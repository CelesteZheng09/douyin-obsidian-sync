import fs from "node:fs";
import path from "node:path";
import readline from "node:readline/promises";
import { pathToFileURL } from "node:url";

const [action, moduleRef, payloadJson] = process.argv.slice(2);
const payload = JSON.parse(payloadJson || "{}");

async function loadPlaywright(ref) {
  if (path.isAbsolute(ref)) {
    return import(pathToFileURL(path.join(ref, "index.mjs")).href);
  }
  return import(ref);
}

const { chromium } = await loadPlaywright(moduleRef);

async function launchBrowser(headless) {
  try {
    return await chromium.launch({ channel: "chrome", headless });
  } catch (chromeError) {
    try {
      return await chromium.launch({ headless });
    } catch (chromiumError) {
      throw new Error(
        `无法启动 Chrome/Chromium。请运行 npm run install-browser。` +
        `\nChrome: ${chromeError}\nChromium: ${chromiumError}`,
      );
    }
  }
}

async function createContext(headless) {
  const browser = await launchBrowser(headless);
  const options = payload.cookiesFile && fs.existsSync(payload.cookiesFile)
    ? { storageState: payload.cookiesFile }
    : {};
  return { browser, context: await browser.newContext(options) };
}

async function login() {
  const browser = await launchBrowser(false);
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("https://www.douyin.com/", { waitUntil: "domcontentloaded" });
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  await rl.question("请在 Chrome 中完成抖音扫码登录，登录成功后回到终端按回车…");
  rl.close();
  await context.storageState({ path: payload.cookiesFile });
  await browser.close();
  process.stderr.write(`登录态已保存到 ${payload.cookiesFile}\n`);
}

async function collect() {
  const { browser, context } = await createContext(payload.headless !== false);
  try {
    const page = await context.newPage();
    const collectionResponses = [];
    page.on("response", async (response) => {
      const url = response.url();
      if (!url.includes("/aweme/v1/web/collects/")) return;
      try {
        collectionResponses.push({ url, status: response.status(), data: await response.json() });
      } catch {
        collectionResponses.push({ url, status: response.status(), data: null });
      }
    });
    await page.goto(payload.profileUrl, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(4000);
    for (const label of ["继续播放", "取消"]) {
      const promptButton = page.getByText(label, { exact: true }).filter({ visible: true }).first();
      if (await promptButton.isVisible().catch(() => false)) {
        await promptButton.click().catch(() => {});
        await page.waitForTimeout(800);
        break;
      }
    }
    let folderClicked = false;
    let clickError = "";
    let collectionTabCandidates = [];
    let reactTabProps = {};
    try {
      let folder = page.getByText(payload.folderName, { exact: true }).filter({ visible: true }).first();
      if (!(await folder.isVisible().catch(() => false))) {
        const collectionTabs = page.getByText("收藏夹", { exact: true });
        collectionTabCandidates = await collectionTabs.evaluateAll((nodes) => nodes.map((node) => ({
          html: node.outerHTML.slice(0, 1000),
          parentHtml: node.parentElement?.outerHTML.slice(0, 1500) || "",
          visible: Boolean(node.getBoundingClientRect().width && node.getBoundingClientRect().height),
        })));
        const collectionTab = page.locator('#semiTabfavorite_folder');
        if (await collectionTab.getAttribute('aria-selected') !== 'true') {
          await collectionTab.click({ timeout: 5000 });
          await page.waitForTimeout(2500);
        }
        await folder.waitFor({ state: 'visible', timeout: 15000 }).catch(() => {});
        if (!(await folder.isVisible().catch(() => false))) {
          reactTabProps = await collectionTab.evaluate((node) => {
            const key = Object.keys(node).find((item) => item.startsWith('__reactProps'));
            const props = key ? node[key] : null;
            const summary = props ? Object.fromEntries(
              Object.entries(props).map(([name, value]) => [name, typeof value]),
            ) : {};
            if (props?.onClick) {
              props.onClick({
                currentTarget: node,
                target: node,
                preventDefault() {},
                stopPropagation() {},
              });
            }
            return summary;
          });
          await page.waitForTimeout(2500);
        }
        folder = page.getByText(payload.folderName, { exact: true }).filter({ visible: true }).first();
      }
      await folder.click({ timeout: 10000 });
      folderClicked = true;
      await page.waitForTimeout(2500);
    } catch (error) {
      clickError = String(error);
      process.stderr.write(`[warn] 未能按名称点中收藏夹 '${payload.folderName}'，直接扫描当前页。\n`);
    }

    let seen = 0;
    for (let i = 0; i < payload.maxScroll; i += 1) {
      await page.mouse.wheel(0, 3000);
      await page.waitForTimeout(1200);
      let visibleLinks = await collectFolderLinks(page);
      let ids = new Set(visibleLinks.map((item) => item.href));
      if (ids.size === seen) {
        await page.mouse.wheel(0, 3000);
        await page.waitForTimeout(1500);
        visibleLinks = await collectFolderLinks(page);
        ids = new Set(visibleLinks.map((item) => item.href));
        if (ids.size === seen) break;
      }
      seen = ids.size;
    }
    const visibleLinks = await collectFolderLinks(page);
    const videoListResponses = collectionResponses.filter(({ url, data }) =>
      url.includes("/collects/video/list/") && Array.isArray(data?.aweme_list),
    );
    const folderResponse = (
      payload.folderId
        ? videoListResponses.find(({ url }) => url.includes(`collects_id=${payload.folderId}`))
        : null
    ) || videoListResponses.at(-1);
    const resolvedFolderId = folderResponse
      ? new URL(folderResponse.url).searchParams.get("collects_id")
      : null;
    const folderItems = folderResponse?.data?.aweme_list?.map((item) => ({
      aweme_id: item.aweme_id,
      aweme_type: item.aweme_type,
      has_images: Boolean(item.images?.length || item.image_post_info),
      desc: item.desc || "",
    })) ?? null;
    const bodyText = (await page.locator("body").innerText()).slice(0, 12000);
    const folderCandidates = await page.getByText(payload.folderName, { exact: true }).evaluateAll((nodes) =>
      nodes.map((node) => ({
        html: node.outerHTML.slice(0, 1000),
        text: (node.innerText || node.textContent || "").trim(),
      })),
    );
    if (payload.debugScreenshot) await page.screenshot({ path: payload.debugScreenshot, fullPage: true });
    if (payload.debugResponses) {
      fs.writeFileSync(payload.debugResponses, JSON.stringify(collectionResponses, null, 2), "utf8");
    }
    process.stdout.write(JSON.stringify({
      visibleLinks,
      folderItems,
      resolvedFolderId,
      folderClicked,
      clickError,
      collectionTabCandidates,
      reactTabProps,
      folderCandidates,
      bodyText,
      collectionResponses: payload.debugResponses ? [] : collectionResponses,
      collectionResponseCount: collectionResponses.length,
      finalUrl: page.url(),
    }));
  } finally {
    await browser.close();
  }
}

async function collectVisibleLinks(page) {
  return page.locator('a[href]').evaluateAll((anchors) => {
    const output = [];
    const seen = new Set();
    for (const anchor of anchors) {
      const rect = anchor.getBoundingClientRect();
      const style = getComputedStyle(anchor);
      if (rect.width <= 0 || rect.height <= 0 || style.visibility === "hidden" || style.display === "none") continue;
      const href = anchor.href || "";
      if (!/(?:modal_id=|\/(?:video|note|article)\/)\d+/.test(href) || seen.has(href)) continue;
      seen.add(href);
      output.push({ href, text: (anchor.innerText || anchor.getAttribute("aria-label") || "").trim() });
    }
    return output;
  });
}

async function collectFolderLinks(page) {
  const panel = page.locator('#semiTabPanelfavorite_folder');
  const scope = await panel.isVisible().catch(() => false) ? panel : page.locator('main,body').first();
  return scope.locator('a[href]').evaluateAll((anchors) => {
    const output = [];
    const seen = new Set();
    for (const anchor of anchors) {
      const rect = anchor.getBoundingClientRect();
      const style = getComputedStyle(anchor);
      if (rect.width <= 0 || rect.height <= 0 || style.visibility === "hidden" || style.display === "none") continue;
      const href = anchor.href || "";
      if (!/(?:modal_id=|\/(?:video|note|article)\/)\d+/.test(href) || seen.has(href)) continue;
      const text = (anchor.innerText || anchor.getAttribute("aria-label") || "").trim();
      if (!text) continue;
      seen.add(href);
      output.push({ href, text });
    }
    return output;
  });
}

async function note() {
  const { browser, context } = await createContext(true);
  try {
    const page = await context.newPage();
    await page.goto(payload.url, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2500);
    for (const keyword of ["展开", "更多"]) {
      try {
        await page.getByText(keyword, { exact: false }).first().click({ timeout: 1500 });
        await page.waitForTimeout(800);
      } catch {}
    }
    const title = ((await page.title()) || "untitled").split(" - ")[0];
    const body = await page.evaluate(() => {
      const nodes = [...document.querySelectorAll("span,p,div")];
      let best = "";
      for (const node of nodes) {
        const text = (node.innerText || "").trim();
        if (text.length > best.length && text.length < 5000) best = text;
      }
      return best;
    });
    process.stdout.write(JSON.stringify({ title, body }));
  } finally {
    await browser.close();
  }
}

async function locateFolder() {
  const { browser, context } = await createContext(false);
  try {
    const page = await context.newPage();
    const network = [];
    const record = (kind, request) => {
      const url = request.url();
      if (!/(favorite|collect|folder|aweme|mix)/i.test(url)) return;
      network.push({ kind, method: request.method(), url, postData: request.postData() || "" });
    };
    page.on("request", (request) => record("request", request));
    await page.goto(payload.profileUrl, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2500);
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    await rl.question("请在 Chrome 中手动进入 收藏 → 收藏夹 → AI，看到内容卡片后回终端按回车…");
    rl.close();
    const visibleLinks = await collectVisibleLinks(page);
    const bodyText = (await page.locator("body").innerText()).slice(0, 12000);
    if (payload.debugScreenshot) await page.screenshot({ path: payload.debugScreenshot, fullPage: false });
    if (payload.debugHtml) fs.writeFileSync(payload.debugHtml, await page.content(), "utf8");
    process.stdout.write(`\n${JSON.stringify({ finalUrl: page.url(), visibleLinks, bodyText, network })}\n`);
  } finally {
    await browser.close();
  }
}

async function captureArticle() {
  const { browser, context } = await createContext(true);
  try {
    const page = await context.newPage();
    const responses = [];
    page.on("response", async (response) => {
      const url = response.url();
      const type = response.request().resourceType();
      if (!['xhr', 'fetch'].includes(type) || !url.includes('douyin.com')) return;
      try {
        responses.push({ url, status: response.status(), data: await response.json() });
      } catch {
        responses.push({ url, status: response.status(), data: null });
      }
    });
    await page.goto(payload.url, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(10000);
    if (payload.outputFile) fs.writeFileSync(payload.outputFile, JSON.stringify(responses, null, 2), "utf8");
    process.stdout.write(JSON.stringify({ count: responses.length, title: await page.title() }));
  } finally {
    await browser.close();
  }
}

async function fetchDetail() {
  const { browser, context } = await createContext(true);
  try {
    const url = `https://www.douyin.com/aweme/v1/web/aweme/detail/?aid=6383&aweme_id=${payload.awemeId}`;
    const response = await context.request.get(url, {
      headers: { Referer: `https://www.douyin.com/note/${payload.awemeId}` },
    });
    const text = await response.text();
    if (payload.outputFile) fs.writeFileSync(payload.outputFile, text, "utf8");
    let data = null;
    try { data = JSON.parse(text); } catch {}
    process.stdout.write(JSON.stringify({
      status: response.status(),
      length: text.length,
      data: payload.outputFile ? null : data,
    }));
  } finally {
    await browser.close();
  }
}

if (action === "login") await login();
else if (action === "collect") await collect();
else if (action === "note") await note();
else if (action === "locate") await locateFolder();
else if (action === "article-api") await captureArticle();
else if (action === "detail-api") await fetchDetail();
else throw new Error(`Unknown action: ${action}`);
