"""Publish four newly rendered camera feeds on worker-local RTSP."""

from threading import Lock, Thread

from .layout import CAMERAS, FPS, RESOLUTION


class CameraStreams:
    def __init__(self):
        import gi

        gi.require_version("Gst", "1.0")
        gi.require_version("GstRtspServer", "1.0")
        from gi.repository import GLib, Gst, GstRtspServer

        Gst.init(None)
        self.gst = Gst
        self.sources = {}
        self.lock = Lock()
        self.context = GLib.MainContext.new()
        self.loop = GLib.MainLoop.new(self.context, False)
        self.server = GstRtspServer.RTSPServer.new()
        self.server.set_address("127.0.0.1")
        self.server.set_service("0")
        mounts = self.server.get_mount_points()
        width, height = RESOLUTION
        pipeline = (
            "appsrc name=frames is-live=true format=time do-timestamp=true "
            "max-buffers=2 max-bytes=0 leaky-type=downstream "
            f"caps=video/x-raw,format=RGB,width={width},height={height},framerate={FPS}/1 "
            "! videoconvert ! video/x-raw,format=I420 "
            f"! x264enc tune=zerolatency speed-preset=ultrafast threads=2 key-int-max={FPS} bitrate=1400 "
            "! h264parse ! rtph264pay name=pay0 pt=96 config-interval=-1"
        )
        Gst.parse_launch(pipeline)
        for camera in range(len(CAMERAS)):
            factory = GstRtspServer.RTSPMediaFactory.new()
            factory.set_shared(True)
            factory.set_launch(f"( {pipeline} )")
            factory.connect("media-configure", self._connect, camera)
            mounts.add_factory(f"/camera-{camera + 1}", factory)
        self.listener = self.server.create_source(None)
        if not self.listener or not self.listener.attach(self.context):
            raise RuntimeError("Couldn't start the hotel camera stream server.")
        port = self.server.get_bound_port()
        self.feeds = [f"rtsp://127.0.0.1:{port}/camera-{i + 1}" for i in range(len(CAMERAS))]
        self.thread = Thread(target=self.loop.run, name="hotel-camera-streams", daemon=True)
        self.thread.start()

    def _connect(self, _factory, media, camera):
        source = media.get_element().get_by_name("frames")
        with self.lock:
            self.sources[camera] = source
        media.connect("unprepared", self._disconnect, camera, source)

    def _disconnect(self, _media, camera, source):
        with self.lock:
            if self.sources.get(camera) == source:
                self.sources.pop(camera)

    def send(self, frames):
        with self.lock:
            sources = tuple(self.sources.items())
        for camera, source in sources:
            data = self.gst.Buffer.new_wrapped(frames[camera])
            data.duration = self.gst.SECOND // FPS
            source.emit("push-buffer", data)

    def close(self):
        self.listener.destroy()
        self.loop.quit()
        self.thread.join(timeout=3)
