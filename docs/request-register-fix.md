# Editable request register

The 0.6.1 update makes **Request register / answer queries** open the editable request section in the current drawing page. It expands the first unresolved request and moves keyboard focus to the register. The JSON export remains available as **Download request data (JSON)**. Existing answers and drawing revisions are preserved.

Update openBIM in Hub, stop and relaunch that module, then refresh the drawing tab. The shared widget also serves the User-designed building module; update that module to receive its pinned dependency change.

Verification used an isolated copy of the HR hospital physical package with a different building ID, so the ordinary provisional workflow was exercised. Clicking the register control exposed the reviewer, information and opening-location form on the same page. Saving a test information note produced revision 2, retained provisional/TBD status and preserved revision history. Twelve drawing-workflow tests and four Hub integration tests passed; JavaScript syntax validation passed. The user's live job data was not modified.
