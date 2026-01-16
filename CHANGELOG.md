# Changelog

All notable changes to LCSC Grabber will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2025-01-16

### Added
- **Custom Categories**: Create and manage custom categories for organizing imported components
  - Each category gets its own symbol library (`.kicad_sym`) and footprint folder (`.pretty`)
  - Category dropdown in import dialog to select destination
  - "+" button to create new categories on the fly
- **3D Model Configuration (Pre-Import)**: Configure 3D model positioning before importing
  - Collapsible "3D Model Config" panel with rotation (X/Y/Z) and offset (X/Y/Z) controls
  - Values are pre-calculated automatically using heuristics (pin 1 detection, centroid calculation)
  - "Reset Auto" button to recalculate default values
- **Library Manager Dialog**: New dialog for managing imported components
  - View all imported components with filtering by category and search
  - Move components between categories
  - Edit 3D model configuration and regenerate footprints
  - Remove components from library
- **Standalone Installers**: Pre-built executables for Windows, macOS, and Linux (no Python required)

### Changed
- Manifest now tracks component category
- 3D model overrides are saved in `model_overrides.json`
- Libraries are now organized per-category instead of single `lcsc_grabber` library

### Fixed
- KiCad 9.0 compatibility (string quoting and fill syntax)
- Absolute path for 3D models instead of environment variable

## [1.0.0] - 2024-12-XX

### Added
- Initial release
- Search components by LCSC part number
- Preview schematic symbols and PCB footprints
- Import symbols, footprints, and 3D models (STEP format)
- Automatic library management with duplicate detection
- Local caching for offline usage
- Support for KiCad 7, 8, and 9
- Dark theme UI with custom styling
