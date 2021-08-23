import logging
import os
import pathlib
import sys
import time
import types
import typing as T

import click
from dotenv import load_dotenv


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


def fake_gpool(scene_cam_intrinsics, app="pipeline", min_calibration_confidence=0.8):
    g_pool = types.SimpleNamespace()
    g_pool.capture = types.SimpleNamespace()
    g_pool.capture.intrinsics = scene_cam_intrinsics
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
def main():
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("numexpr").setLevel(logging.WARNING)
    logging.getLogger("OpenGL").setLevel(logging.WARNING)

    load_dotenv()
    if "CORE_SHARED_MODULES_LOCATION" in os.environ:
        sys.path.append(os.environ["CORE_SHARED_MODULES_LOCATION"])
    else:
        logging.warning("Core source location unknown. Imports might fail.")

    mapping_methods_by_label = available_mapping_methods()
    mapping_method_label = click.prompt(
        "Choose gaze mapping method",
        type=click.Choice(mapping_methods_by_label.keys(), case_sensitive=True),
    )
    mapping_method = mapping_methods_by_label[mapping_method_label]
    patch_plugin_notify_all(mapping_method)

    ref_data_loc = os.environ["REF_DATA_LOCATION"]
    pupil_data_loc = os.environ["RECORDING_LOCATION"] + "/pupil.pldata"
    intrinsics_loc = os.environ["RECORDING_LOCATION"] + "/world.intrinsics"
    calibrate_and_validate(ref_data_loc, pupil_data_loc, intrinsics_loc, mapping_method)


if __name__ == "__main__":
    main()
