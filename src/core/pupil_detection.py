import sys
import os
import logging
import types
from os.path import exists
import cv2
import numpy as np

from core.pipeline import fake_gpool, load_intrinsics

import click
from dotenv import load_dotenv


def pl_detection_on_video(recording_path, g_pool):
    roi = None
    detector2d = None
    detector3d = None
    timestamps_path = recording_path[0:recording_path.rindex('.')]+"_timestamps.npy"
    timestamps = np.load(timestamps_path)
    id = int(recording_path[0:recording_path.rindex('.')][-1])
    topic = str(id)
    
    from pupil_detector_plugins.detector_2d_plugin import Detector2DPlugin
    from pupil_detector_plugins.pye3d_plugin import Pye3DPlugin
    from roi import Roi
    import file_methods as fm
    
    vidcap = cv2.VideoCapture(recording_path)
    total_frames = vidcap.get(cv2.CAP_PROP_FRAME_COUNT)
    datum_list = {'2d':[],'3d':[]}
    success,frame = vidcap.read()
    count = 0
    while success:
        timestamp = timestamps[count]
        bgr = frame[:,:,0]
        bgr = bgr.copy(order='C')
        gray = frame[:,:,0]
        gray = gray.copy(order='C')
        height, width = gray.shape
        if detector2d is None:
            g_pool.display_mode = "n/a"
            g_pool.eye_id = id
            roi = Roi(g_pool=g_pool, frame_size=(width, height), bounds=(0, 0, width, height))
            detector2d = Detector2DPlugin(g_pool=g_pool)
            detector3d = Pye3DPlugin(g_pool=g_pool)
        pupil_frame = lambda: None
        setattr(pupil_frame, 'gray', gray)
        setattr(pupil_frame, 'bgr', bgr)
        setattr(pupil_frame, 'width', width)
        setattr(pupil_frame, 'height', height)
        setattr(pupil_frame, 'timestamp', timestamp)
        pupil_datum = detector2d.detect(pupil_frame)
        pupil_datum = fm.Serialized_Dict(python_dict=pupil_datum)
        pupil3d_datum = detector3d.detect(pupil_frame,
            **{'previous_detection_results': [pupil_datum]}
        )
        datum_list['2d'].append(pupil_datum)
        datum_list['3d'].append(fm.Serialized_Dict(python_dict=pupil3d_datum))
        
        count += 1
        if count % 1000 == 0:
            logging.info(f"{count}/{int(total_frames)}")
        success,frame = vidcap.read()
    
    return datum_list


def get_datum_dicts_from_eyes(file_names, recording_loc, scene_cam_intrinsics):
    recording_dicts = []
    for file_name in file_names:
        recording_path = recording_loc+"/"+file_name
        if not exists(recording_path):
            logging.error(f"Recording {file_name} does not exist.")
        else:
            logging.debug(f"Recording {file_name} exists!")
            recording_dicts.append(pl_detection_on_video(recording_path, fake_gpool(scene_cam_intrinsics)))
            logging.info(f"Completed detection of recording {file_name}")
    return recording_dicts


def save_datums_to_pldata(datums, save_location):
    import player_methods as pm
    import file_methods as fm
    pupil_data_store = pm.PupilDataCollector()
    for eyeId in range(len(datums)):
        for detector in datums[eyeId]:
            for datum in datums[eyeId][detector]:
                timestamp = datum["timestamp"]
                pupil_data_store.append(f"pupil.{eyeId}.{detector}", datum, timestamp)  # possibly?
    data = pupil_data_store.as_pupil_data_bisector()
    data.save_to_file(save_location, "offline_pupil")
    session_data = {}
    session_data["detection_status"] = ["complete", "complete"]
    session_data["version"] = 4
    cache_path = os.path.join(save_location, "offline_pupil.meta")
    fm.save_object(session_data, cache_path)


@click.command()
@click.option(
    "--core_shared_modules_loc",
    required=False,
    type=click.Path(exists=True),
    envvar="CORE_SHARED_MODULES_LOCATION",
)
@click.option(
    "--recording_loc",
    required=True,
    type=click.Path(exists=True),
    envvar="RECORDING_LOCATION",
)
@click.option(
    "--ref_data_loc",
    required=True,
    type=click.Path(exists=True),
    envvar="REF_DATA_LOCATION",
)
def main(core_shared_modules_loc, recording_loc, ref_data_loc):
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("numexpr").setLevel(logging.WARNING)
    logging.getLogger("OpenGL").setLevel(logging.WARNING)
    
    if core_shared_modules_loc:
        sys.path.append(core_shared_modules_loc)
    else:
        logging.warning("Core source location unknown. Imports might fail.")
    
    scene_cam_intrinsics_loc = recording_loc + "/world.intrinsics"
    scene_cam_intrinsics = load_intrinsics(scene_cam_intrinsics_loc)
    datums = get_datum_dicts_from_eyes(['eye0.mp4', 'eye1.mp4'], recording_loc, scene_cam_intrinsics)
    logging.info(f"Completed detection of pupils.")
    save_datums_to_pldata(datums, recording_loc+'/offline_data')
    logging.info("Saved pldata to disk.")


if __name__ == "__main__":
    load_dotenv()
    main()
