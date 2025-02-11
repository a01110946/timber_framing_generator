# Timber Framing Generator

A Python-based tool for automated timber framing generation and analysis, integrating Revit with Rhino/Grasshopper through Rhino.Inside.Revit.

## Features

- Extracts wall data from Revit models
- Analyzes wall components and openings
- Generates timber framing solutions
- Decomposes walls into structural cells
- Creates detailed framing geometry
- Provides visualization tools

## Project Structure

```
TIMBER_FRAMING_GENERATOR/
├── docs/                    # Documentation files
├── scripts/                 # Utility scripts
├── src/                    # Source code
│   ├── cell_decomposition/  # Cell analysis and segmentation
│   ├── framing_elements/   # Framing component generation
│   ├── utils/              # Utility functions
│   └── wall_data/          # Wall data extraction and processing
└── tests/                  # Test files
```

## Dependencies

- Python 3.9+
- Rhino.Inside.Revit
- Rhinoceros 7+
- Revit 2021+
- Grasshopper

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/timber-framing-generator.git
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up Rhino.Inside.Revit according to the [official documentation](https://github.com/mcneel/rhino.inside-revit).

## Usage

Detailed usage instructions and examples can be found in the [documentation](docs/usage.md).

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- McNeel Associates for Rhino.Inside.Revit
- Autodesk for the Revit API
- Contributors and maintainers
