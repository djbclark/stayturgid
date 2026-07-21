#!/usr/bin/env node
// @generated
"use strict";
// @ts-nocheck
// Check rendered dashboard pages for visible HTML-as-text, missing JS elements,
// and common template escaping failures.
//
// Usage: node just/tools/rendered_dom_check.js [url...]
// Default: http://127.0.0.1:4097/
var __awaiter =
  (this && this.__awaiter) ||
  function (thisArg, _arguments, P, generator) {
    function adopt(value) {
      return value instanceof P
        ? value
        : new P(function (resolve) {
            resolve(value);
          });
    }
    return new (P || (P = Promise))(function (resolve, reject) {
      function fulfilled(value) {
        try {
          step(generator.next(value));
        } catch (e) {
          reject(e);
        }
      }
      function rejected(value) {
        try {
          step(generator["throw"](value));
        } catch (e) {
          reject(e);
        }
      }
      function step(result) {
        result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected);
      }
      step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
  };
const urls = process.argv.slice(2).length ? process.argv.slice(2) : ["http://127.0.0.1:4097/"];
function checkPage(page, url) {
  return __awaiter(this, void 0, void 0, function* () {
    const issues = [];
    try {
      yield page.goto(url, { waitUntil: "domcontentloaded", timeout: 15000 });
    } catch (err) {
      issues.push({ type: "error", msg: `Page load failed: ${err.message}` });
      return issues;
    }
    // Wait a beat for HTMX to render dynamic content
    yield page.evaluate(() => new Promise((r) => setTimeout(r, 2000)));
    // 1. Visible HTML-in-text: walk text nodes for literal < or HTML-like patterns
    const htmlInText = yield page.evaluate(() => {
      const results = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
      let node;
      while ((node = walker.nextNode())) {
        const text = node.textContent.trim();
        if (!text) continue;
        if (text.includes("<") || /&lt;|&gt;|&amp;lt;/.test(text)) {
          const el = node.parentElement;
          const tag = el
            ? `<${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${el.className ? "." + el.className.split(" ").join(".") : ""}>`
            : "?";
          results.push({
            text: text.substring(0, 120),
            context: `${tag}: "${text.substring(0, 60)}..."`,
          });
        }
      }
      return results;
    });
    for (const r of htmlInText) {
      issues.push({ type: "html-in-text", msg: r.context });
    }
    // 2. Check HTMX-loaded sections populated
    const htmxEmpty = yield page.evaluate(() => {
      const empty = [];
      document.querySelectorAll("[hx-get]").forEach((el) => {
        const text = el.textContent.trim().toLowerCase();
        if (text === "" || text === "loading…" || text === "loading..." || text.includes("htmx-indicator")) {
          empty.push(`HTMX target <${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}> still empty`);
        }
      });
      return empty;
    });
    for (const m of htmxEmpty) {
      issues.push({ type: "htmx-empty", msg: m });
    }
    // 3. Visible JS template markers ({{ }}, {% %})
    const templateMarkers = yield page.evaluate(() => {
      const results = [];
      const re = /\{\{|%\}|\{\%|%}/;
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
      let node;
      while ((node = walker.nextNode())) {
        if (re.test(node.textContent)) {
          const el = node.parentElement;
          const tag = el ? el.tagName.toLowerCase() : "?";
          results.push(`Unrendered template marker in <${tag}>: "${node.textContent.substring(0, 80)}"`);
        }
      }
      return results;
    });
    for (const m of templateMarkers) {
      issues.push({ type: "template-marker", msg: m });
    }
    return issues;
  });
}
(() =>
  __awaiter(void 0, void 0, void 0, function* () {
    const puppeteer = require("puppeteer");
    let browser;
    try {
      browser = yield puppeteer.launch({
        headless: true,
        args: ["--no-sandbox", "--disable-setuid-sandbox"],
      });
    } catch (err) {
      console.error(`FAIL: Could not launch browser: ${err.message}`);
      process.exit(1);
    }
    let totalIssues = 0;
    for (const url of urls) {
      const page = yield browser.newPage();
      console.log(`\n${url}`);
      const issues = yield checkPage(page, url);
      yield page.close();
      if (issues.length === 0) {
        console.log("  OK");
      } else {
        for (const issue of issues) {
          totalIssues++;
          const icon = issue.type === "error" ? "✖" : issue.type === "htmx-empty" ? "⚠" : "!";
          console.log(`  ${icon} [${issue.type}] ${issue.msg}`);
        }
      }
    }
    yield browser.close();
    if (totalIssues > 0) {
      console.log(`\n${totalIssues} issue(s) found`);
      process.exit(1);
    }
  }))();
