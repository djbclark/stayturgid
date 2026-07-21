// @generated
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * One-shot helper: write legacy mode marker and show next steps.
 * Run from AutoJs6 when setting up a new device.
 */
const config = require("../lib/config.js");
const notify = require("../lib/notify.js");
config.ensureDirs();
files.write(config.SD_ROOT + "/state/automation_mode.txt", "autojs6\n");
const msg = "stayturgid: enable AutoJs6 accessibility, then run main.js (or rely on Termux:Boot).";
toast(msg);
notify.show("stayturgid AutoJs6", msg);
