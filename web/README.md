# Star Pop in the browser

This is an installable web app for the same game as the Mac version. It uses the webcam and MediaPipe Pose Landmarker (lite model, one or two people). The page is static: no game server.

An Xbox Kinect cannot be used here. Browsers do not speak the Kinect’s USB protocol. Plug in a webcam, or use the camera on a Mac, iPad, or iPhone. The Kinect app remains `./run.sh` in the repository root.

## Run it locally

From `web/`:

```bash
npm install
npm run dev
```

`npm install` puts MediaPipe’s wasm files in `node_modules`. The dev and build scripts copy those into `public/mediapipe/wasm` and download `pose_landmarker_lite.task` into `public/models/`. The page then loads both from its own origin. After the first load, the service worker keeps the app, the model, and the wasm so it works offline.

Open the URL Vite prints (usually http://127.0.0.1:5173/). Choose stars or meteors, one or two players, and the P1 suit. **Start camera** asks for the webcam. **Demo bodies** plays with two built-in poses and no camera. **S** or **View** cycles the overlay. **Esc** or **Menu** returns to the start screen. When a meteor round ends, press **Again**, **R**, **Space**, or hold both hands up.

## Install it

The built app is a PWA.

- **Chrome on a Mac:** open the Pages URL, then the install icon in the address bar (or the menu item “Install Star Pop”).
- **Safari on a Mac:** File → Add to Dock.
- **iPhone or iPad:** Safari → Share → Add to Home Screen. The icon is the one in `public/icons/apple-touch-icon.png`.

Install after one online visit so the service worker can cache the model and wasm. Later launches can be offline. The camera still has to be on the device.

## GitHub Pages

The workflow `.github/workflows/pages.yml` builds `web/` with the base path `/starcamgame/` and deploys the `dist` folder.

Pages does not turn itself on. On GitHub:

1. Open the repository **Settings**.
2. Open **Pages** in the left sidebar.
3. Under **Build and deployment**, set **Source** to **GitHub Actions**.

The address is:

https://richard747.github.io/starcamgame/

A push to `main` that changes `web/` runs the workflow. You can also open the **Actions** tab, choose **Deploy Star Pop web**, and run it by hand.

## Checks

```bash
npm test
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```
