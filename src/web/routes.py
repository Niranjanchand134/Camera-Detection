import os
import time
import mimetypes
from datetime import datetime
from flask import Blueprint, render_template, Response, request, jsonify, send_from_directory, send_file, make_response
from src.config.settings import get_settings
from src.camera.manager import get_camera_manager
from src.detection.detector import get_detector
from src.audio.player import get_audio_player
from src.storage.recorder import get_recorder, VideoRecorder
from src.storage.database import get_db

main_bp = Blueprint("main", __name__)


def init_routes(app, manager=None, detector=None, audio_player=None, recorder=None, db=None):
    settings = get_settings()
    manager = manager or get_camera_manager(settings)
    detector = detector or get_detector(settings)
    audio_player = audio_player or get_audio_player(settings)
    recorder = recorder or get_recorder(settings=settings)
    db = db or get_db()

    @main_bp.route("/")
    @main_bp.route("/live")
    def live_view():
        cameras = manager.get_camera_names()
        statuses = manager.get_all_statuses()
        active_cat = detector.get_category() or "off"
        rec_status = recorder.get_status()

        # Check audio capabilities per camera
        cam_audio_caps = {cam: audio_player.has_audio(cam) for cam in cameras}

        return render_template(
            "live.html",
            page="live",
            cameras=cameras,
            statuses=statuses,
            active_category=active_cat,
            recording_status=rec_status,
            cam_audio_caps=cam_audio_caps
        )

    @main_bp.route("/records")
    @main_bp.route("/reports")
    def records_view():
        cameras = manager.get_camera_names()
        stats = db.get_stats()
        return render_template(
            "records.html",
            page="records",
            cameras=cameras,
            stats=stats
        )

    # Video stream feeds (MJPEG)
    @main_bp.route("/video_feed/grid")
    def video_feed_grid():
        return Response(
            manager.generate_mjpeg_stream(target="grid", fps=15, w=960, h=540),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )

    @main_bp.route("/video_feed/<cam_name>")
    def video_feed_single(cam_name):
        if cam_name not in manager.get_camera_names():
            return "Camera not found", 404
        return Response(
            manager.generate_mjpeg_stream(target=cam_name, fps=15, w=960, h=540),
            mimetype="multipart/x-mixed-replace; boundary=frame"
        )

    # Live In-Browser Audio Stream (HTTP chunked MP3)
    @main_bp.route("/audio_feed/<cam_name>")
    def audio_feed(cam_name):
        if cam_name not in manager.get_camera_names():
            return "Camera not found", 404
        return Response(
            audio_player.generate_mp3_stream(cam_name),
            mimetype="audio/mpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Accel-Buffering": "no"
            }
        )

    # API: System status & live telemetry
    @main_bp.route("/api/status")
    def api_status():
        rec_stat = recorder.get_status()
        all_dets = detector.get_all_detections()
        cam_statuses = manager.get_all_statuses()
        cam_names = manager.get_camera_names()
        audio_caps = {c: audio_player.has_audio(c) for c in cam_names}

        return jsonify({
            "cameras": cam_statuses,
            "active_category": detector.get_category() or "off",
            "recording": rec_stat,
            "audio_capabilities": audio_caps,
            "detections": all_dets,
            "total_cameras": len(cam_statuses),
            "online_cameras": sum(1 for c in cam_statuses.values() if c["status"] == "online")
        })

    # API: Control AI Detection
    @main_bp.route("/api/control/detection", methods=["POST"])
    def api_control_detection():
        data = request.get_json(force=True, silent=True) or {}
        category = data.get("category", "off")
        detector.set_category(category)
        return jsonify({"status": "success", "active_category": detector.get_category() or "off"})

    # API: Control Video Recording (with Audio Muxing)
    @main_bp.route("/api/control/recording", methods=["POST"])
    def api_control_recording():
        data = request.get_json(force=True, silent=True) or {}
        action = data.get("action", "toggle")
        target = data.get("camera", "all")

        if action == "start":
            res = recorder.start(manager, target=target)
        elif action == "stop":
            res = recorder.stop(target=target)
        else:
            res = recorder.toggle(manager, target=target)

        return jsonify({
            "status": "success",
            "details": res,
            "recording": recorder.get_status()
        })

    # API: Query Records & Reports
    @main_bp.route("/api/records")
    def api_get_records():
        camera = request.args.get("camera")
        category = request.args.get("category")
        start_time = request.args.get("start_time")
        end_time = request.args.get("end_time")
        plate = request.args.get("plate")
        min_speed = request.args.get("min_speed")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))

        records_data = db.get_events(
            camera=camera,
            category=category,
            start_time=start_time,
            end_time=end_time,
            plate=plate,
            min_speed=min_speed,
            page=page,
            per_page=per_page
        )
        stats = db.get_stats()
        return jsonify({
            "status": "success",
            "data": records_data,
            "stats": stats
        })

    # API: Export CSV Report
    @main_bp.route("/api/records/export")
    def api_export_records():
        camera = request.args.get("camera")
        category = request.args.get("category")
        start_time = request.args.get("start_time")
        end_time = request.args.get("end_time")
        plate = request.args.get("plate")
        min_speed = request.args.get("min_speed")

        csv_data = db.export_csv(
            camera=camera,
            category=category,
            start_time=start_time,
            end_time=end_time,
            plate=plate,
            min_speed=min_speed
        )

        filename = f"camera_detection_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response = make_response(csv_data)
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-type"] = "text/csv; charset=utf-8"
        return response

    # API: List Recorded Videos (Supports Typing Search, Date & Camera Filtering)
    @main_bp.route("/api/recordings")
    def api_get_recordings():
        query = request.args.get("q")
        target_date = request.args.get("date")
        target_camera = request.args.get("camera")

        files = recorder.get_recordings(query=query, target_date=target_date, target_camera=target_camera)

        return jsonify({
            "status": "success",
            "recordings": files,
            "total": len(files)
        })

    # API: Delete single detection record
    @main_bp.route("/api/records/<int:event_id>", methods=["DELETE", "POST"])
    def api_delete_record(event_id):
        success = db.delete_event(event_id)
        stats = db.get_stats()
        return jsonify({"status": "success" if success else "error", "deleted_id": event_id, "stats": stats})

    # API: Delete all detection records
    @main_bp.route("/api/records/all", methods=["DELETE", "POST"])
    def api_delete_all_records():
        count = db.delete_all_events()
        stats = db.get_stats()
        return jsonify({"status": "success", "deleted_count": count, "stats": stats})

    # API: Delete single video recording
    @main_bp.route("/api/recordings/<path:rel_path>", methods=["DELETE", "POST"])
    def api_delete_recording(rel_path):
        deleted = recorder.delete_recording(rel_path)
        return jsonify({"status": "success" if deleted else "not_found", "path": rel_path})

    # API: Delete all recordings (with optional search filter)
    @main_bp.route("/api/recordings/all", methods=["DELETE", "POST"])
    def api_delete_all_recordings():
        query = request.args.get("q")
        target_date = request.args.get("date")
        target_camera = request.args.get("camera")
        count = recorder.delete_all_recordings(query=query, target_date=target_date, target_camera=target_camera)
        return jsonify({"status": "success", "deleted_count": count})

    # Video File Delivery (HTTP Range Requests for smooth browser playback & seeking)
    @main_bp.route("/video_recordings/<path:rel_path>")
    @main_bp.route("/recordings/<path:rel_path>")
    def serve_recording(rel_path):
        safe_rel = os.path.normpath(rel_path).replace("\\", "/").lstrip("/")
        if ".." in safe_rel:
            return "Invalid path", 400

        full_path = os.path.join(settings.recordings_dir, safe_rel)
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            return "File not found", 404

        return send_file(
            full_path,
            mimetype="video/mp4",
            conditional=True
        )

    @main_bp.route("/snapshots/<filename>")
    def serve_snapshot(filename):
        return send_from_directory(settings.snapshots_dir, filename)

    app.register_blueprint(main_bp)
