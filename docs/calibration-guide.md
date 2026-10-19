# Room, seat and camera calibration guide

## 1. Create the room (Rooms & seat map)
Enter name, real width/depth in metres, rows x columns. Seats are generated as `R{row}-C{col}` (1-based, e.g. `R2-C4`) with evenly spaced positions (`x`,`y` are 0-1 fractions of room width/depth). Click a seat to edit its position, or mark it unmonitored. For irregular layouts use `PUT /api/rooms/{id}/seats` with your own list. **Removing a seat deletes its camera regions.**

## 2. Outline seats on the camera image (Calibration)
1. Pick the camera and room; start the camera (a frame is needed to draw on).
2. Choose a seat, click 3+ points around where that seat/person appears, **Finish region**. Repeat per seat. Outline the area where a seated person's body would appear, not just the chair.
3. Set visibility: *Fully visible*; *Partially visible* (a person can be seen but an empty look proves nothing, so vacant is reported as UNCERTAIN); *Not adequately visible* (seat is shown as OCCLUDED, not analysed).
4. **Save regions.** If the camera is running this applies immediately.
Several cameras may cover one seat; each seat is still counted once (see occupancy.md).

## 3. Capture the empty-room baseline
With nobody in view, same lighting as the exam, click **Capture baseline** (camera must be CONNECTED). Recapture if the camera is moved, zoom/exposure changes, or lighting differs. Without a baseline every seat is UNCERTAIN, never VACANT.

## Try it with synthetic videos
`python scripts/make_room_demo_videos.py`, create a 1x3 room, add a video-file camera `empty_room.avi`, draw seat A over the left part and seat B over the right part (or use the exact polygons in the script header via the API), start, capture the baseline, stop, change the source to `person_seat_a.avi`, start: seat A should turn OCCUPIED, seat B VACANT.
