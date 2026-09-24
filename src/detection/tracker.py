import math
import time


class CentroidSpeedTracker:
    def __init__(self, pixels_per_meter: float = 20.0, max_dist_px: float = 120.0, ttl: float = 2.0):
        self.pixels_per_meter = max(1e-3, pixels_per_meter)
        self.max_dist_px = max_dist_px
        self.ttl = ttl
        # tracks[camera_name][category] = list of track objects
        self.tracks = {}

    def update(self, camera_name: str, category: str, boxes_px: list, now: float = None) -> list:
        if now is None:
            now = time.time()

        cam_tracks = self.tracks.setdefault(camera_name, {}).setdefault(category, [])
        centroids = [((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0) for b in boxes_px]
        speeds = [None] * len(boxes_px)
        matched = set()

        for i, c in enumerate(centroids):
            best_j, best_dist = -1, self.max_dist_px
            for j, t in enumerate(cam_tracks):
                if j in matched:
                    continue
                d = math.hypot(c[0] - t["centroid"][0], c[1] - t["centroid"][1])
                if d < best_dist:
                    best_dist, best_j = d, j

            if best_j != -1:
                t = cam_tracks[best_j]
                dt = now - t["time"]
                if dt > 0.05:
                    dist_m = best_dist / self.pixels_per_meter
                    speed_kmh = (dist_m / dt) * 3.6
                    prev = t.get("speed")
                    if prev is not None:
                        speed_kmh = 0.6 * prev + 0.4 * speed_kmh
                    speeds[i] = speed_kmh
                    t["speed"] = speed_kmh
                t["centroid"] = c
                t["time"] = now
                matched.add(best_j)
            else:
                cam_tracks.append({"centroid": c, "time": now, "speed": None})

        # Remove stale tracks
        cam_tracks[:] = [t for t in cam_tracks if now - t["time"] < self.ttl]
        return speeds

    def clear_camera(self, camera_name: str):
        if camera_name in self.tracks:
            self.tracks[camera_name] = {}
