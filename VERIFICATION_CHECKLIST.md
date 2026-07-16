# UI & Structural Quality Gate Checklist

## 1. Boundary & Data Stretch Stress-Test
- [ ] **Extreme Value Test:** Inject a product name with 50+ characters (e.g., "Aspirin Coated Tablets USP 500mg Extra Strength Non-Drowsy Max"). Does the text wrap cleanly, or does it blowout widget boundaries?
- [ ] **Viewport Boundary Test:** Resize the application window to its minimum allowed size. Are all buttons, entries, and sidebar controls completely visible and reachable via scrolling?
- [ ] **Dynamic Scaling Test:** Open the window on a lower-resolution layout. Is the properties panel completely intact?

## 2. Process Independence & Subprocesses
- [ ] **Asynchronous Lock Check:** Ensure the main application UI thread remains 100% responsive (no spinning cursor/freeze) while a barcode or label template is processing or printing.
- [ ] **Console Leak Check:** Verify that no hidden command prompt windows spawn when launching secondary windows or subprocesses.