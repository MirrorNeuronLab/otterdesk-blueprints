# Visualizer dependencies

The image installs [PyLabRobot 0.2.1](https://github.com/PyLabRobot/pylabrobot)
under its MIT license. The blueprint serves its packaged visualizer with local
asset URLs, a same-origin WebSocket, and a small workspace layout that fits the
deck and collapses the native inspector when the pane is narrow.

At image build, `prepare_visualizer.py` downloads the visualizer's dependencies
at the versions and SHA-256 hashes in `visualizer-assets.json`. Their distributed
license comments remain intact. Bootstrap 5.1.3, Bootstrap Icons 1.8.3,
Konva 8.4.3, JSZip 3.7.1 and html2canvas 1.4.1 use MIT licenses; JSZip is dual
MIT/GPLv3 and this image uses its MIT grant. Bootstrap Icons fonts use MIT.
Sources: [Bootstrap](https://github.com/twbs/bootstrap),
[Bootstrap Icons](https://github.com/twbs/icons),
[Konva](https://github.com/konvajs/konva),
[JSZip](https://github.com/Stuk/jszip),
[html2canvas](https://github.com/niklasvh/html2canvas).

The browser loads these assets from the blueprint listener. It does not contact
CDNs. No dependency download occurs during a simulated procedure.

The PyLabRobot wheel omits its visualizer PNGs. The same build inventory fetches
the logo and three tool images from upstream commit
`4d4a83086ed26775afffe6d73356cc85ec5af93d`, each with its own SHA-256 check.
They retain PyLabRobot's MIT license.
