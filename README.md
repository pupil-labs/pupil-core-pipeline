## Usage

### Development installation

Requires Python 3.8 or newer

```sh
pip install git+https://github.com/papr/pupil-core-pipeline
```

### Recalculate accuracy and precision for recorded calibrations

This utility reads the reference and pupil data that was collected during calibrations
of a given recording, and recalculates the accuracy and precision of it. Optionally,
it can export the values to a json file.

```
Usage: pupil_core_accuracy [OPTIONS] RECORDING_LOC

Options:
  --core_shared_modules_loc PATH
  -o, --output FILE               If given, results will be written as json to
                                  this location, e.g. `output.json`
  --help                          Show this message and exit.
```

### Post-hoc pipeline execution
Execute from the root of this repository
```sh
python -m core.pipeline
```
See `python -m core.pipeline --help` for help. Alternatively, the options can be read
from the `.env` file.

### Config from environment variables
Some of the command line arguments can be set a environment variables. This allows
reading these values from an `.env` file with the following content:

```
CORE_SHARED_MODULES_LOCATION={Full path to .../pupil/pupil_src/shared_modules}
RECORDING_LOCATION={Full path to a recording}
REF_DATA_LOCATION=${RECORDING_LOCATION}/offline_data/reference_locations.msgpack
```
