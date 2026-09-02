# Microduck attribution

The bundled web application derives from the Microduck RL playground supplied
with the local `duck` project. Its included README attributes the Microduck
models and trained policies to [Pollen Robotics](https://www.pollen-robotics.com/)
and the upstream [microduck](https://github.com/pollen-robotics/microduck) and
[microduck_rl](https://github.com/pollen-robotics/microduck_rl) repositories.

This blueprint keeps the upstream simulator assets, model files, and
`package-lock.json` in `payloads/web_app`; it excludes local `node_modules`
and generated `dist` output. The existing browser-loaded MuJoCo and ONNX WASM
dependencies remain CDN-hosted. Consult the upstream projects for their
applicable asset, model, and policy terms before redistributing them.
