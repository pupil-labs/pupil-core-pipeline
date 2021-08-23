## Usage

### Development installation

```sh
# 1. clone repository and change curren working directory to clone
# 2. Update pip
pip install -U pip
# 3. Editable install of core pipeline
pip install -e .
```

#### Dependencies
1. Install [Pupil Core](https://github.com/pupil-labs/pupil/) source code and dependencies
2. Create `.env` file with the following content:
```
CORE_SHARED_MODULES_LOCATION={Full path to .../pupil/pupil_src/shared_modules}
RECORDING_LOCATION={Full path to a recording}
REF_DATA_LOCATION=${RECORDING_LOCATION}/offline_data/reference_locations.msgpack
```

### Pipeline execution
Execute from the root of this repository
```sh
python -m core.pipeline
```