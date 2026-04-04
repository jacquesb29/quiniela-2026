from __future__ import annotations

from dataclasses import asdict
import math


def compute_backtest_summary(
    fixtures,
    teams,
    top_scores,
    *,
    BacktestMetricsCls,
    fixture_has_final_result,
    copy_states,
    empty_persistent_payload,
    resolve_fixture_names,
    context_from_fixture,
    fixture_stage_name,
    predict_match,
    normalize_team_state,
    actual_regular_time_outcome,
    actual_advancement_outcome,
    confidence_bucket,
    apply_state_updates,
    brier_decomposition,
    summarize_temporal_windows,
    avg_or_none,
    temporal_cv_fold_size,
):
    completed = []
    for fixture in fixtures:
        if fixture.get("projection_only"):
            continue
        if not fixture_has_final_result(fixture):
            continue
        completed.append(dict(fixture))
    completed.sort(key=lambda item: (item.get("kickoff_utc") or "", str(item.get("id", ""))))

    if not completed:
        return asdict(
            BacktestMetricsCls(
                completed_matches=0,
                regular_time_samples=0,
                advancement_samples=0,
                favorite_hit_rate=None,
                top1_score_hit_rate=None,
                top3_score_hit_rate=None,
                brier_result=None,
                logloss_result=None,
                brier_advance=None,
                logloss_advance=None,
                market_logloss_result=None,
                calibration_buckets=[],
            )
        )

    states = copy_states(empty_persistent_payload(teams))
    result_brier = []
    result_logloss = []
    market_result_logloss = []
    advance_brier = []
    advance_logloss = []
    favorite_hits = 0
    favorite_total = 0
    top1_hits = 0
    top3_hits = 0
    regular_samples = 0
    advance_samples = 0
    calibration = {}
    regular_predictions = []
    regular_outcomes = []
    regular_hits = []

    for fixture in completed:
        try:
            fixture = resolve_fixture_names(fixture, teams)
        except SystemExit:
            continue
        ctx = context_from_fixture(fixture, teams, states)
        stage = fixture_stage_name(fixture)
        prediction = predict_match(
            teams,
            fixture["team_a"],
            fixture["team_b"],
            ctx,
            top_scores=top_scores,
            include_advancement=stage != "group",
            show_factors=False,
            state_a=normalize_team_state(states.get(fixture["team_a"], {})),
            state_b=normalize_team_state(states.get(fixture["team_b"], {})),
        )

        actual_outcome = actual_regular_time_outcome(fixture)
        if actual_outcome is not None:
            probs = {"a": prediction.win_a, "draw": prediction.draw, "b": prediction.win_b}
            regular_samples += 1
            favorite_total += 1
            predicted_outcome = max(probs.items(), key=lambda item: item[1])[0]
            is_hit = 1 if predicted_outcome == actual_outcome else 0
            if is_hit:
                favorite_hits += 1
            regular_hits.append(is_hit)
            p_actual = max(probs[actual_outcome], 1e-12)
            result_logloss.append(-math.log(p_actual))
            result_brier.append(
                ((probs["a"] - (1.0 if actual_outcome == "a" else 0.0)) ** 2
                 + (probs["draw"] - (1.0 if actual_outcome == "draw" else 0.0)) ** 2
                 + (probs["b"] - (1.0 if actual_outcome == "b" else 0.0)) ** 2) / 3.0
            )
            regular_predictions.append((probs["a"], probs["draw"], probs["b"]))
            regular_outcomes.append(actual_outcome)
            if fixture.get("market_prob_a") is not None and fixture.get("market_prob_draw") is not None and fixture.get("market_prob_b") is not None:
                market_probs = {
                    "a": float(fixture["market_prob_a"]),
                    "draw": float(fixture["market_prob_draw"]),
                    "b": float(fixture["market_prob_b"]),
                }
                market_result_logloss.append(-math.log(max(market_probs[actual_outcome], 1e-12)))

            actual_score = f"{int(fixture['actual_score_a'])}-{int(fixture['actual_score_b'])}"
            predicted_scores = [score for score, _ in prediction.exact_scores]
            if predicted_scores:
                if predicted_scores[0] == actual_score:
                    top1_hits += 1
                if actual_score in predicted_scores[:3]:
                    top3_hits += 1

            bucket = confidence_bucket(float(prediction.statistical_depth.get("confidence_index", 0.0))) if prediction.statistical_depth else "<50%"
            bucket_state = calibration.setdefault(bucket, {"n": 0, "hit": 0, "avg_conf": 0.0})
            bucket_state["n"] += 1
            bucket_state["hit"] += 1 if predicted_outcome == actual_outcome else 0
            bucket_state["avg_conf"] += float(prediction.statistical_depth.get("confidence_index", 0.0)) if prediction.statistical_depth else 0.0

        actual_advance = actual_advancement_outcome(fixture, teams)
        if actual_advance is not None and prediction.advance_a is not None and prediction.advance_b is not None:
            probs = {"a": prediction.advance_a, "b": prediction.advance_b}
            advance_samples += 1
            p_actual = max(probs[actual_advance], 1e-12)
            advance_logloss.append(-math.log(p_actual))
            advance_brier.append(
                ((probs["a"] - (1.0 if actual_advance == "a" else 0.0)) ** 2
                 + (probs["b"] - (1.0 if actual_advance == "b" else 0.0)) ** 2) / 2.0
            )

        apply_state_updates(teams, states, fixture, ctx, prediction)

    calibration_buckets = []
    bucket_order = ["<50%", "50-59%", "60-69%", "70-79%", "80%+"]
    for bucket in bucket_order:
        payload = calibration.get(bucket)
        if not payload:
            continue
        n = payload["n"]
        calibration_buckets.append(
            {
                "bucket": bucket,
                "matches": n,
                "avg_confidence": payload["avg_conf"] / n,
                "hit_rate": payload["hit"] / n,
            }
        )

    brier_parts = brier_decomposition(regular_predictions, regular_outcomes) if regular_predictions else None
    temporal_windows = summarize_temporal_windows(
        result_logloss,
        result_brier,
        regular_hits,
        fold_size=temporal_cv_fold_size,
    )

    metrics = BacktestMetricsCls(
        completed_matches=len(completed),
        regular_time_samples=regular_samples,
        advancement_samples=advance_samples,
        favorite_hit_rate=(favorite_hits / favorite_total) if favorite_total else None,
        top1_score_hit_rate=(top1_hits / regular_samples) if regular_samples else None,
        top3_score_hit_rate=(top3_hits / regular_samples) if regular_samples else None,
        brier_result=avg_or_none(result_brier),
        logloss_result=avg_or_none(result_logloss),
        brier_advance=avg_or_none(advance_brier),
        logloss_advance=avg_or_none(advance_logloss),
        market_logloss_result=avg_or_none(market_result_logloss),
        calibration_buckets=calibration_buckets,
        brier_reliability=(brier_parts or {}).get("reliability"),
        brier_resolution=(brier_parts or {}).get("resolution"),
        brier_uncertainty=(brier_parts or {}).get("uncertainty"),
        temporal_cv_logloss=temporal_windows.get("logloss"),
        temporal_cv_brier=temporal_windows.get("brier"),
        temporal_cv_accuracy=temporal_windows.get("accuracy"),
    )
    return asdict(metrics)
