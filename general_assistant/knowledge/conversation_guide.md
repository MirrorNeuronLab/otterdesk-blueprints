# Computer Use conversation guide

This is workflow guidance, not evidence of work already completed.

Describe the app and result you want. Give recipients and message contents when
requesting a send. Instructions can be supplied at setup or in Chat when a run
asks for a task. A capability question does not start work.
For a task restricted to one named app, bind `target_app_bundle_id` with the run
task (Chrome is `com.google.Chrome`, Safari is `com.apple.Safari`). The run then
permits input only in that app. Leave the scope empty for a task that explicitly
needs several apps. Missing app identity should be clarified rather than guessed.

For a read-only walkthrough, ask “Open https://example.com and tell me the page
heading. Do not submit anything.” The bundled examples/demo.json uses this task
on your real browser. There is no simulated desktop or sample login.

Grant Accessibility and Screen Recording to the separate mn computer use app.
OtterDesk does not need these grants. The helper is a headless-style native tool
service with a permission window and a CU stop menu. It requires macOS 14+,
24 GB RAM, the catalog's vision model on the system default LLM provider, and Membrane.

When asked to sign in or handle verification, take over in the app and reply
when ready. Do not paste secrets into Chat. The agent stops capturing and
controlling while waiting, then checks the screen again. An ambiguous reply
should prompt one focused clarification, not a guessed action.

Review answer.md for the actual observed result and computer-use-audit.json for
action types. If an outcome is unknown, check the desktop before retrying.
Membrane navigation hints help future tasks but never establish a current login
or completed send. Ask what was observed, what remains, or which help is needed.
EmbeddingGemma 2 also recalls similar successful app layouts from Job-private
screenshots. Images can include visible content; they stay out of exported
results. Historical field hints are always matched against current controls.
After a commit input, inspect the result instead of entering another action.
