timber_framing_generator/  <-- Your project's root directory
├── .github/
│   └── workflows/
│       └── feature-branch-automation.yml  <-- GitHub Actions workflow
├── src/
│   └── timber_framing_generator/  <-- Your actual Python package
│       ├── __init__.py          <-- Makes this a package
│       ├── cell_decomposition/
│       │   ├── __init__.py
│       │   ├── cell_segmentation.py
│       │   ├── cell_types.py
│       │   └── cell_visualizer.py
│       ├── config/
│       │   ├── __init__.py
│       │   ├── assembly.py
│       │   └── framing.py
│           └── units.py
│       ├── dev_utils/
│       │   ├── __init__.py
│       │   └── reload_modules.py
│       ├── framing_elements/
│       │   ├── __init__.py
│       │   ├── framing_generator.py
│       │   ├── framing_geometry.py
│       │   ├── header_cripples.py
│       │   ├── header_parameters.py
│       │   ├── headers.py
│       │   ├── king_studs.py
│       │   ├── location_data.py
│       │   ├── plate_geometry.py
│       │   ├── plate_parameters.py
│       │   ├── plates.py
│       │   ├── sill_cripples.py
│       │   ├── sill_parameters.py
│       │   ├── sills.py
│       │   ├── studs.py          <-- This file was missing before, now it's here
│       │   ├── timber_element.py
│       │   └── trimmers.py
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── coordinate_systems.py
│       │   ├── data_extractor.py
│       │   └── geometry_helpers.py
│           └── units.py      <-- This file was missing before, now it's here
│       ├── wall_data/
│       │   ├── __init__.py
│       │   ├── revit_data_extractor.py
│       │   ├── revit_walls.py
│           ├── config.py
│       │   ├── wall_helpers.py
│       │   ├── wall_input.py
│       │   └── wall_selector.py
│       └── main.py
├── tests/
│   ├── __init__.py         <--  Good practice to have this
│   ├── conftest.py       <--  pytest fixtures (e.g., wall_data)
│   └── framing_elements/
│       ├── __init__.py     <-- Important for pytest to discover tests
│       └── test_plates.py  <--  Your test file
├── .gitignore            <--  Contains at least .venv/
├── pyproject.toml        <--  Project metadata and dependencies
├── README.md             <--  Your project's README
├── requirements.txt      <--  ONLY for workflow dependencies (pytest, flake8, requests)
└── scripts/
    ├── export_to_revit.py
    └── visualize_wall_assembly.py