import logging
import os
import pathlib
import sys
import time
import types
import typing as T
from math import floor

import click
from dotenv import load_dotenv

from . import _default_shared_modules_loc


def save_gaze_data(gaze, gaze_ts, recording_loc, export=True):
    import file_methods as fm

    directory = os.path.join(recording_loc, "pipeline-gaze-mappings")
    os.makedirs(directory, exist_ok=True)
    file_name = "pipeline"  # self._gaze_mapping_file_name(gaze_mapper)
    with fm.PLData_Writer(directory, file_name) as writer:
        for gaze_ts_uz, gaze_uz in zip(gaze_ts, gaze):
            writer.append_serialized(
                gaze_ts_uz, topic="gaze", datum_serialized=gaze_uz.serialized
            )
    logging.info(f"Gaze data saved to {directory}.")

    if export:
        import player_methods as pm
        from raw_data_exporter import Gaze_Positions_Exporter

        export_directory = os.path.join(recording_loc, "pipeline-exports")
        os.makedirs(export_directory, exist_ok=True)
        gaze_bisector = pm.Bisector(gaze, gaze_ts)
        gaze_positions_exporter = Gaze_Positions_Exporter()
        gaze_positions_exporter.csv_export_write(
            positions_bisector=gaze_bisector,
            timestamps=gaze_ts,
            export_window=[
                gaze_bisector.data_ts[0] - 1,
                gaze_bisector.data_ts[len(gaze_bisector.data_ts) - 1] + 1,
            ],
            export_dir=export_directory,
        )
        logging.info(f"Gaze data exported to {export_directory}.")


def map_pupil_data(gazer, pupil_data):
    import file_methods as fm

    logging.info("Mapping pupil data to gaze data.")
    gaze = []
    gaze_ts = []

    first_ts = pupil_data[0]["timestamp"]
    last_ts = pupil_data[-1]["timestamp"]
    ts_span = last_ts - first_ts
    curr_ts = first_ts

    prev_prog = 0.0
    for gaze_datum in gazer.map_pupil_to_gaze(pupil_data):
        curr_ts = max(curr_ts, gaze_datum["timestamp"])
        progress = (curr_ts - first_ts) / ts_span
        if floor(progress * 100) != floor(prev_prog * 100):
            logging.info(f"Gaze Mapping Progress: {floor(progress*100)}%")
        prev_prog = progress
        # result = (curr_ts, fm.Serialized_Dict(gaze_datum))

        gaze.append(fm.Serialized_Dict(gaze_datum))
        gaze_ts.append(curr_ts)

    logging.info("Pupil data mapped to gaze data.")
    return gaze, gaze_ts


def calibrate_and_validate(
    ref_loc, pupil_loc, scene_cam_intrinsics_loc, mapping_method
):
    ref_data = load_ref_data(ref_loc)
    logging.debug(f"Loaded {len(ref_data)} reference locations")
    pupil = load_pupil_data(pupil_loc)
    logging.debug(f"Loaded {len(pupil.data)} pupil positions")
    scene_cam_intrinsics = load_intrinsics(scene_cam_intrinsics_loc)
    logging.debug(f"Loaded scene camera intrinsics: {scene_cam_intrinsics}")
    gazer = fit_gazer(mapping_method, ref_data, pupil.data, scene_cam_intrinsics)
    return gazer, pupil.data


def load_ref_data(ref_loc):
    import file_methods as fm

    ref = fm.load_object(ref_loc)
    assert ref["version"] == 1, "unexpected reference data format"
    return [{"screen_pos": r[0], "timestamp": r[2]} for r in ref["data"]]


def load_pupil_data(pupil_loc):
    import file_methods as fm

    pupil_loc = pathlib.Path(pupil_loc)
    pupil = fm.load_pldata_file(pupil_loc.parent, pupil_loc.stem)
    return pupil


def load_intrinsics(intrinsics_loc, resolution=(640, 480)):
    import camera_models as cm

    intrinsics_loc = pathlib.Path(intrinsics_loc)
    return cm.Camera_Model.from_file(
        intrinsics_loc.parent, intrinsics_loc.stem, resolution
    )


def available_mapping_methods():
    import gaze_mapping

    return {
        gazer.label: gazer
        for gazer in gaze_mapping.user_selectable_gazer_classes_posthoc()
    }


def fit_gazer(mapping_method, ref_data, pupil_data, scene_cam_intrinsics):
    return mapping_method(
        fake_gpool(scene_cam_intrinsics),
        calib_data={"ref_list": ref_data, "pupil_list": pupil_data},
    )


def fake_gpool(scene_cam_intrinsics, app="pipeline", min_calibration_confidence=0.0):
    g_pool = types.SimpleNamespace()
    g_pool.capture = types.SimpleNamespace()
    g_pool.capture.intrinsics = scene_cam_intrinsics
    g_pool.capture.frame_size = scene_cam_intrinsics.resolution
    g_pool.get_timestamp = time.perf_counter
    g_pool.app = app
    g_pool.min_calibration_confidence = min_calibration_confidence
    return g_pool


def patch_plugin_notify_all(plugin_class):
    def log_notification(self, notification):
        """Patches Plugin.notify_all of gazer class"""
        logging.info(f"Notification: {notification['subject']} ({notification.keys()})")

    logging.debug(f"Patching {plugin_class.notify_all}")
    plugin_class.notify_all = log_notification


@click.command()
@click.option("--skip_pupil_detection", is_flag=True)
@click.option(
    "--core_shared_modules_loc",
    required=False,
    type=click.Path(exists=True),
    envvar="CORE_SHARED_MODULES_LOCATION",
    default=_default_shared_modules_loc(),
)
@click.option(
    "-rec",
    "--recording_loc",
    required=True,
    type=click.Path(exists=True),
    envvar="RECORDING_LOCATION",
)
@click.option(
    "-ref",
    "--ref_data_loc",
    required=True,
    type=click.Path(exists=True),
    envvar="REF_DATA_LOCATION",
)
def main(skip_pupil_detection, core_shared_modules_loc, recording_loc, ref_data_loc):
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("numexpr").setLevel(logging.WARNING)
    logging.getLogger("OpenGL").setLevel(logging.WARNING)

    if core_shared_modules_loc:
        sys.path.append(core_shared_modules_loc)
    else:
        logging.warning("Core source location unknown. Imports might fail.")

    mapping_methods_by_label = available_mapping_methods()
    mapping_method_label = click.prompt(
        "Choose gaze mapping method",
        type=click.Choice(mapping_methods_by_label.keys(), case_sensitive=True),
    )
    mapping_method = mapping_methods_by_label[mapping_method_label]
    patch_plugin_notify_all(mapping_method)

    if not skip_pupil_detection:
        from core.pupil_detection import perform_pupil_detection

        logging.info("Performing pupil detection on eye videos. This may take a while.")
        perform_pupil_detection(recording_loc)
        logging.info("Pupil detection complete.")

    pupil_data_loc = recording_loc + "/offline_data/offline_pupil.pldata"
    intrinsics_loc = recording_loc + "/world.intrinsics"
    calibrated_gazer, pupil_data = calibrate_and_validate(
        ref_data_loc, pupil_data_loc, intrinsics_loc, mapping_method
    )
    gaze, gaze_ts = map_pupil_data(calibrated_gazer, pupil_data)
    save_gaze_data(gaze, gaze_ts, recording_loc)


if __name__ == "__main__":
    load_dotenv()
    main()
