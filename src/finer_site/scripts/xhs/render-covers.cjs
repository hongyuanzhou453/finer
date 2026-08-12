/**
 * 把 covers.html 里每个 .cv 导出为 1242x1656 PNG（小红书 3:4）。
 * 复用 dashboard 已装的 playwright + chromium：
 *
 *   NODE_PATH=../../../finer_dashboard/node_modules node render-covers.cjs [outDir]
 *
 * 导出前强制跑三条红线断言（见 docs/specs/2026-08-13-xiaohongshu-coldstart-plan.md §4.5）：
 *   1. .num 含 % 时，.unit 必须写样本量，且字号 ≥ .num 的 22%
 *   2. 数据型封面必须有非空 .disclaim
 *   3. 主标 / 主数必须完整落在黄金带 y∈[414,1242]（小红书会重裁成 4:3）
 * 任一不过就抛错拒绝导出——红线是断言，不是建议。
 */
const path = require("path");
const fs = require("fs");
const { chromium } = require("playwright");

(async () => {
  const outDir = path.resolve(process.argv[2] || "./out");
  fs.mkdirSync(outDir, { recursive: true });
  const src = "file://" + path.resolve(__dirname, "covers.html");

  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1400, height: 1800 },
    deviceScaleFactor: 1,
  });
  await page.goto(src, { waitUntil: "load" });

  const problems = await page.evaluate(({ GOLD_TOP, GOLD_BOT }) => {
    const errs = [];
    document.querySelectorAll(".cv").forEach((cv) => {
      const name = cv.dataset.name || "(unnamed)";
      const num = cv.querySelector(".num");
      const unit = cv.querySelector(".unit");
      const disclaim = cv.querySelector(".disclaim");
      const head = cv.querySelector(".head");

      // 红线 1：比率必须并排样本量
      if (num && /%/.test(num.textContent)) {
        if (!unit || !unit.textContent.trim()) {
          errs.push(`${name}: .num 含 % 但 .unit 缺失`);
        } else {
          if (!/\d/.test(unit.textContent)) errs.push(`${name}: .unit 未写样本量`);
          const ns = parseFloat(getComputedStyle(num).fontSize);
          const us = parseFloat(getComputedStyle(unit).fontSize);
          if (us < ns * 0.22) errs.push(`${name}: .unit ${us}px < .num ${ns}px 的 22%`);
        }
      }
      // 红线 2：数据型必须有非空免责
      if (num && !(disclaim && disclaim.textContent.trim())) {
        errs.push(`${name}: 数据型封面缺 .disclaim，拒绝导出`);
      }
      // 红线 3：主标/主数必须完整落在黄金带
      const box = cv.getBoundingClientRect();
      const focal = head || num;
      if (focal) {
        const f = focal.getBoundingClientRect();
        const top = f.top - box.top;
        const bot = f.bottom - box.top;
        if (top < GOLD_TOP || bot > GOLD_BOT) {
          errs.push(`${name}: 主标出黄金带 [${GOLD_TOP},${GOLD_BOT}]，实际 [${Math.round(top)},${Math.round(bot)}]`);
        }
      }
      // 禁用词自查（图像通道会被 OCR）
      const BANNED = ["跟单", "荐股", "稳赚", "必涨", "抄底", "买入", "卖出", "推荐", "最准", "排名", "预测未来"];
      const text = cv.textContent;
      BANNED.forEach((w) => { if (text.includes(w)) errs.push(`${name}: 出现禁用词「${w}」`); });
    });
    return errs;
  }, { GOLD_TOP: 414, GOLD_BOT: 1242 });

  if (problems.length) {
    console.error("红线断言未通过，拒绝导出：");
    problems.forEach((p) => console.error("  ✗ " + p));
    await browser.close();
    process.exit(1);
  }

  const cards = await page.$$(".cv");
  for (const card of cards) {
    const name = await card.evaluate((el) => el.dataset.name);
    const file = path.join(outDir, `${name}.png`);
    await card.screenshot({ path: file });
    console.log("✓ " + path.relative(process.cwd(), file));
  }
  console.log(`\n${cards.length} 张封面已导出到 ${outDir}（1242×1656，3:4）`);
  await browser.close();
})();
