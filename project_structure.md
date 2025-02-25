TIMBER_FRAMING_GENERATOR/
├── docs/
│   ├── architecture.md
│   ├── design_specification.md
│   └── usage.md
├── scripts/
│   ├── export_to_revit.py
│   └── visualize_wall_assembly.py
├── src/
│   ├── cell_decomposition/
│   │   ├── __init__.py
│   │   ├── cell_segmentation.py
│   │   ├── cell_types.py
│   │   └── cell_visualizer.py
│   ├── config/                    # New modular configuration package
│   │   ├── __init__.py
│   │   ├── assembly.py
│   │   ├── framing.py
│   │   └── units.py
│   ├── framing_elements/
│   │   ├── __init__.py
│   │   ├── framing_generator.py
│   │   ├── framing_geometry.py
│   │   ├── king_studs.py
│   │   ├── location_data.py
│   │   ├── plate_geometry.py
│   │   ├── plate_parameters.py
│   │   ├── plates.py
│   │   ├── studs.py
│   │   └── timber_element.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── data_extractor.py
│   │   ├── geometry_helpers.py
│   │   └── units.py
│   ├── wall_data/
│   │   ├── __init__.py
│   │   ├── revit_data_extractor.py
│   │   ├── revit_walls.py
│   │   ├── wall_helpers.py
│   │   ├── wall_input.py
│   │   └── wall_selector.py
│   ├── __init__.py
│   ├── config.py
│   └── main.py
├── tests/                         # Testing directory (to be developed)
│   ├── framing_elements/
│   │   ├── __init__.py
│   │   └── test_plates.py
│   └── __init__.py
├── .gitignore
├── README.md
└── requirements.txt