# Monitoring condition check

Camera: {camera_id}
Condition to check: {target_description}

Inspect only the supplied frame or frame batch. Decide whether the visible
condition is met. If the condition asks for a change, use only a reliable
before-and-after view in this batch. Ignore unrelated subjects, signs,
reflections, and guesses about identity or intent. Confidence describes the
certainty of your yes/no decision, including a confident absence. An occluded,
blurred, or insufficient view has low confidence.

Return only a JSON object with `condition_met` (boolean) and `confidence`
(number from 0 to 1). Do not explain or include other fields.
