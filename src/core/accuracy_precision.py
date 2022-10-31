import json
import logging
import pathlib
import sys
from collections import defaultdict
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional

import click
from dotenv import load_dotenv
from rich import print
from rich.progress import track
from typing_extensions import Protocol, TypedDict

from . import _default_shared_modules_loc


@click.command()
@click.option(
    "--core_shared_modules_loc",
    required=False,
    type=click.Path(exists=True),
    envvar="CORE_SHARED_MODULES_LOCATION",
    default=_default_shared_modules_loc(),
)
@click.argument(
    "recording_loc",
    required=True,
    type=click.Path(
        exists=True, path_type=pathlib.Path, dir_okay=True, file_okay=False
    ),
    envvar="RECORDING_LOCATION",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=pathlib.Path, dir_okay=False, file_okay=True),
    help="If given, results will be written as json to this location",
)
def main(
    core_shared_modules_loc: str,
    recording_loc: pathlib.Path,
    output: Optional[pathlib.Path],
):
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("numexpr").setLevel(logging.WARNING)
    logging.getLogger("OpenGL").setLevel(logging.WARNING)

    if core_shared_modules_loc:
        sys.path.append(core_shared_modules_loc)
        logging.debug(f"Added {core_shared_modules_loc} to `sys.path`")
    else:
        logging.warning("Core source location unknown. Imports might fail.")

    print(f"Processing {recording_loc}")
    calibrations = list(_extract_calibrations(recording_loc / "notify.pldata"))
    print(f"Found {len(calibrations)} calibrations")

    results: List[AccuracyPrecisionResult] = []
    for calib in track(
        calibrations, description="Calculating accuracy and precision..."
    ):
        acc_prec = calib.accuracy_precision()
        print(f"Calibration at time {calib.timestamp}")
        print(
            f"Accuracy: {acc_prec.accuracy.result:.3f} deg "
            f"({acc_prec.accuracy.num_used}/{acc_prec.accuracy.num_total} "
            "samples used)"
        )
        print(
            f"Precision: {acc_prec.precision.result:.3f} deg "
            f"({acc_prec.precision.num_used}/{acc_prec.precision.num_total} "
            "samples used)"
        )
        results.append(acc_prec)
    if output:
        output.write_text(
            json.dumps(
                [
                    calib.result_as_dict(result)
                    for calib, result in zip(calibrations, results)
                ],
                default=float,
                indent=4,
            )
        )
        print(f"Wrote results to {output.resolve()}")


class CalculationResult(Protocol):
    result: float
    num_used: int
    num_total: int


class AccuracyPrecisionResult(Protocol):
    accuracy: CalculationResult
    precision: CalculationResult


@dataclass
class Calibration:
    recording: pathlib.Path
    setup: "CalibrationSetup"
    result: "CalibrationResult"

    def accuracy_precision(self) -> AccuracyPrecisionResult:
        from accuracy_visualizer import Accuracy_Visualizer
        from camera_models import Camera_Model
        from gaze_mapping import gazer_classes_by_class_name, registered_gazer_classes

        intrinsics = Camera_Model.all_from_file(self.recording, "world")
        if len(intrinsics) == 0:
            raise ValueError("No intrinsics found! Aborting")
        elif len(intrinsics) > 1:
            raise ValueError(
                f"{len(intrinsics)} intrinsics found: {list(intrinsics.keys())}. "
                "Unclear which one to use. Aborting."
            )
        camera = next(iter(intrinsics.values()))

        g_pool = SimpleNamespace(capture=SimpleNamespace(intrinsics=camera))
        gazers = gazer_classes_by_class_name(registered_gazer_classes())
        return Accuracy_Visualizer.calc_acc_prec_errlines(
            g_pool,
            gazer_class=gazers[self.result["gazer_class_name"]],
            gazer_params=self.result["params"],
            pupil_list=self.setup["calib_data"]["pupil_list"],
            ref_list=self.setup["calib_data"]["ref_list"],
            intrinsics=camera,
            outlier_threshold=5.0,
        )

    @property
    def timestamp(self) -> float:
        return self.result["timestamp"]

    def result_as_dict(self, result: Optional[AccuracyPrecisionResult] = None):
        if result is None:
            result = self.accuracy_precision()
        return {
            "recording": str(self.recording),
            "timestamp": self.timestamp,
            "accuracy": {
                "degrees": result.accuracy.result,
                "num_used": result.accuracy.num_used,
                "num_total": result.accuracy.num_total,
            },
            "precision": {
                "degrees": result.precision.result,
                "num_used": result.precision.num_used,
                "num_total": result.precision.num_total,
            },
        }


def _extract_calibrations(path: pathlib.Path) -> Iterable["Calibration"]:
    from file_methods import load_pldata_file

    data = load_pldata_file(path.parent, path.stem)

    calibrations: Calibrations = defaultdict(list)
    for notification, _, topic in zip(*data):
        if topic == "notify.calibration.setup.v2":
            calibrations["setups"].append(notification)
        elif topic == "notify.calibration.result.v2":
            calibrations["results"].append(notification)

    len_set = len(calibrations["setups"])
    len_res = len(calibrations["results"])
    assert (
        len_set == len_res
    ), f"Number of setups ({len_set}) vs results ({len_res}) does not match. Aborting."

    yield from (
        Calibration(path.parent, s, r)
        for s, r in zip(calibrations["setups"], calibrations["results"])
    )


class Calibrations(TypedDict):
    setups: List["CalibrationSetup"]
    results: List["CalibrationResult"]


class CalibrationNotification(TypedDict):
    gazer_class_name: str
    timestamp: float
    record: bool
    version: int
    subject: str
    topic: str


class CalibrationSetup(CalibrationNotification):
    calib_data: Any


class CalibrationResult(CalibrationNotification):
    params: Any


if __name__ == "__main__":
    load_dotenv()
    main()
