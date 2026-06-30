# Radiology Case Demo Fixture

This folder contains mock, de-identified radiology case materials for testing PPTKiller's radiology case-driven mode.

All clinical details and images are fictional. The PNG files are synthetic mock scans, not real patient images.

## Suggested Upload

Upload the whole folder contents, or upload these files in batches:

1. `case-index.csv`
2. Each `Case-*/Case-*_case-note.md`
3. Each `Case-*/*.png`

## Expected App Behavior

PPTKiller should:

- Detect three case materials.
- Build case cards for typical, differential, and pitfall teaching roles.
- Mark the materials as de-identified.
- Recognize CT as the modality.
- Keep diagnosis, pathology, and follow-up facts grounded in the case notes.
- Avoid treating the mock images as real diagnostic evidence.

