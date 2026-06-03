from artiq.experiment import *


class AndorSnap(EnvExperiment):
    """Snap a frame from the Andor camera into a dataset and (optionally) open
    the Solis-style applet.

    Host-only: talks to the Andor NDSP controller over RPC via the ``andor``
    device. Works against real hardware or the ``--simulation`` controller.
    """

    def build(self):
        self.setattr_device("andor")
        self.setattr_device("ccb")
        self.setattr_argument("exposure_s", NumberValue(0.01, min=1e-4, max=30.0,
                                                         unit="s", precision=4))
        self.setattr_argument("frames", NumberValue(1, min=1, max=1000, step=1,
                                                     precision=0))
        self.setattr_argument("open_solis_applet", BooleanValue(False))

    def run(self):
        info = self.andor.get_device_info()
        sim = self.andor.is_simulation()
        print("Andor: %s%s" % (info.get("camera_name") or info.get("model"),
                               " [SIMULATION]" if sim else ""))

        actual = self.andor.set_exposure(float(self.exposure_s))
        print("Exposure set to %.4g s" % actual)

        n = int(self.frames)
        for i in range(n):
            frame = self.andor.snap()
            self.set_dataset("andor.image", frame, broadcast=True)
            if n > 1:
                print("Frame %d/%d: shape=%s, min=%d, max=%d"
                      % (i + 1, n, frame.shape, int(frame.min()), int(frame.max())))

        # Built-in image applet (works with any frame-producing source).
        self.ccb.issue("create_applet", "Andor Image",
                       "${artiq_applet}image andor.image",
                       group="andor")

        # Optional: launch the live Solis-style applet, pointed at the same
        # NDSP host/port as registered in the device_db.
        if self.open_solis_applet:
            db = self.get_device_db()["andor"]
            host, port = db.get("host", "localhost"), db.get("port", 3287)
            repo_root = "${artiq_root}/repository/applets/andor_solis.py"
            self.ccb.issue(
                "create_applet", "Andor Solis",
                "python3 " + repo_root
                + " --andor-server %s --andor-port %d --img andor.image"
                % (host, port),
                group="andor")

        print("Done. Frame written to dataset 'andor.image'.")
