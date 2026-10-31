# Fictional Project Board — original product notes

## Page and loading
- The project board must open from the navigation menu.
- Selecting a project loads all seven persisted read-only details, not a placeholder ID.
- Show an explicit error state when the project request fails.

## Actions
- Save notes must persist the edit across a full reload.
- Export XLSX is disabled until saving succeeds, and the downloaded file must include the saved notes.
- Viewer permissions must reject write attempts even when the caller bypasses the page.
