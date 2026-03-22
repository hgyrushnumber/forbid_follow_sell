// content.js - 页面内交互版本（最终整合版）
// 功能：
// 1. 在 seller.ozon.ru 页面注入 UI
// 2. 读取 Excel 中的 SKU 列
// 3. 导航菜单
// 4. 逐个 SKU 搜索
// 5. 逐个 SKU 上传同一张图片
//
// 重要前提：
// 请在 manifest.json 中先加载 libs/xlsx.full.min.js，再加载 content.js
//
// 示例：
// "content_scripts": [
//   {
//     "matches": ["https://seller.ozon.ru/*"],
//     "js": ["libs/xlsx.full.min.js", "content.js"],
//     "run_at": "document_idle"
//   }
// ]

(function () {
  const CONFIG = {
    uiId: "ozon-kick-ui",
    statusId: "automation-status",
    initDelayMs: 2000,

    menuFindTimeoutMs: 4000,
    menuRetryCount: 3,
    menuRetryGapMs: 1500,
    clickAfterScrollDelayMs: 500,
    afterClickWaitMs: 2500,

    generalPollIntervalMs: 400,
    textPollIntervalMs: 300,
    waitTimeoutMs: 15000,

    searchResultTimeoutMs: 10000,
    uploadFinishedTimeoutMs: 20000,

    debugKeepUI: true,
  };

  let automationRunning = false;

  init();

  function init() {
    window.addEventListener("load", () => {
      setTimeout(() => {
        tryInitUI();
      }, CONFIG.initDelayMs);
    });

    hookHistoryEvents();

    window.addEventListener("popstate", () => {
      setTimeout(() => {
        tryInitUI();
      }, 800);
    });
  }

  function hookHistoryEvents() {
    const rawPushState = history.pushState;
    const rawReplaceState = history.replaceState;

    history.pushState = function (...args) {
      const result = rawPushState.apply(this, args);
      setTimeout(() => {
        tryInitUI();
      }, 800);
      return result;
    };

    history.replaceState = function (...args) {
      const result = rawReplaceState.apply(this, args);
      setTimeout(() => {
        tryInitUI();
      }, 800);
      return result;
    };
  }

  function tryInitUI() {
    if (!window.location.href.includes("seller.ozon.ru")) {
      return;
    }

    if (document.getElementById(CONFIG.uiId)) {
      return;
    }

    createFileSelectionUI();
  }

  function createFileSelectionUI() {
    if (document.getElementById(CONFIG.uiId)) {
      return;
    }

    const uiContainer = document.createElement("div");
    uiContainer.id = CONFIG.uiId;
    uiContainer.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 999999;
        background: white;
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        width: 360px;
        font-family: system-ui, sans-serif;
        border: 1px solid #e5e7eb;
        color: #111827;
      `;

    uiContainer.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="margin:0;font-size:16px;color:#374151;">Ozon 踢跟助手</h3>
          <button id="close-ui" style="background:#f3f4f6;border:none;padding:4px 8px;border-radius:4px;cursor:pointer;color:#6b7280;">
            关闭
          </button>
        </div>
  
        <div style="margin-bottom:12px;">
          <label style="display:block;margin-bottom:4px;font-size:14px;color:#374151;">Excel 文件（含 SKU 列）</label>
          <input
            type="file"
            id="excel-file"
            accept=".xlsx,.xls"
            style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:4px;box-sizing:border-box;"
          >
        </div>
  
        <div style="margin-bottom:12px;">
          <label style="display:block;margin-bottom:4px;font-size:14px;color:#374151;">要上传的图片</label>
          <input
            type="file"
            id="image-file"
            accept="image/*"
            style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:4px;box-sizing:border-box;"
          >
        </div>
  
        <div style="margin-bottom:12px;">
          <button
            id="start-automation"
            style="width:100%;padding:10px;background:#3b82f6;color:white;border:none;border-radius:6px;font-size:14px;cursor:pointer;"
          >
            开始自动化
          </button>
        </div>
  
        <div
          id="${CONFIG.statusId}"
          style="font-size:12px;color:#6b7280;min-height:56px;line-height:1.5;white-space:pre-wrap;word-break:break-word;"
        >
          准备就绪
        </div>
  
        <div style="font-size:11px;color:#9ca3af;margin-top:8px;">
          请确保已登录 Ozon 卖家后台
        </div>
      `;

    document.body.appendChild(uiContainer);

    const closeBtn = document.getElementById("close-ui");
    const startBtn = document.getElementById("start-automation");

    if (closeBtn) {
      closeBtn.onclick = () => {
        uiContainer.remove();
      };
    }

    if (startBtn) {
      startBtn.onclick = async () => {
        if (automationRunning) {
          setStatus("⏳ 自动化正在执行中，请勿重复点击", "#d97706");
          return;
        }

        automationRunning = true;
        startBtn.disabled = true;
        startBtn.style.opacity = "0.7";
        startBtn.style.cursor = "not-allowed";

        try {
          await handleAutomation();
        } finally {
          automationRunning = false;
          startBtn.disabled = false;
          startBtn.style.opacity = "1";
          startBtn.style.cursor = "pointer";
        }
      };
    }
  }

  async function handleAutomation() {
    try {
      const excelInput = document.getElementById("excel-file");
      const imageInput = document.getElementById("image-file");

      const excelFile =
        excelInput && excelInput.files ? excelInput.files[0] : null;
      const imageFile =
        imageInput && imageInput.files ? imageInput.files[0] : null;

      if (!excelFile || !imageFile) {
        setStatus("❌ 请同时选择 Excel 文件和图片", "#dc2626");
        return;
      }

      setStatus("📊 正在读取 Excel 文件...", "#059669");
      const skus = await parseExcelFile(excelFile);

      if (!Array.isArray(skus) || skus.length === 0) {
        setStatus("❌ Excel 文件中未找到有效 SKU", "#dc2626");
        return;
      }

      setStatus(`✅ 找到 ${skus.length} 个 SKU，开始执行自动化...`, "#059669");
      await executeAutomation(skus, imageFile);

      setStatus("🎉 自动化执行完毕！请检查页面结果。", "#059669");

      if (!CONFIG.debugKeepUI) {
        setTimeout(() => {
          const ui = document.getElementById(CONFIG.uiId);
          if (ui) ui.remove();
        }, 3000);
      }
    } catch (error) {
      console.error("自动化失败:", error);
      setStatus(`❌ 错误: ${getErrorMessage(error)}`, "#dc2626");
    }
  }

  async function parseExcelFile(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();

      reader.onload = (e) => {
        try {
          if (typeof XLSX === "undefined") {
            reject(
              new Error(
                "XLSX 库未加载，请检查 manifest.json 是否先加载 libs/xlsx.full.min.js",
              ),
            );
            return;
          }

          const data = e && e.target ? e.target.result : null;
          if (!data) {
            reject(new Error("Excel 文件内容为空"));
            return;
          }

          const skus = parseExcelData(data);
          resolve(skus);
        } catch (error) {
          reject(error);
        }
      };

      reader.onerror = () => reject(new Error("Excel 文件读取失败"));
      reader.readAsArrayBuffer(file);
    });
  }

  function parseExcelData(data) {
    const workbook = XLSX.read(data, { type: "array" });

    if (!workbook || !workbook.SheetNames || workbook.SheetNames.length === 0) {
      throw new Error("Excel 文件中没有可用工作表");
    }

    const firstSheetName = workbook.SheetNames[0];
    const firstSheet = workbook.Sheets[firstSheetName];

    if (!firstSheet) {
      throw new Error("未找到第一个工作表");
    }

    const rows = XLSX.utils.sheet_to_json(firstSheet, { header: 1 });

    if (!rows || rows.length < 2) {
      throw new Error("Excel 数据为空或只有表头");
    }

    const headerRow = rows[0].map((v) =>
      String(v || "")
        .trim()
        .toLowerCase(),
    );

    const candidateHeaders = [
      "sku",
      "seller sku",
      "seller_sku",
      "sku id",
      "商品sku",
      "商品 sku",
      "商家sku",
      "商家 sku",
      "货号",
      "编码",
      "артикул",
      "sku продавца",
    ];

    let skuColIndex = -1;

    for (let i = 0; i < headerRow.length; i++) {
      const cell = headerRow[i];
      if (!cell) continue;

      if (candidateHeaders.includes(cell)) {
        skuColIndex = i;
        break;
      }

      if (cell.includes("sku") || cell.includes("артикул")) {
        skuColIndex = i;
        break;
      }
    }

    if (skuColIndex === -1) {
      throw new Error(
        "未找到 SKU 列，请检查 Excel 表头是否包含 SKU / 商家SKU / Артикул",
      );
    }

    const skus = rows
      .slice(1)
      .map((row) => row[skuColIndex])
      .filter((v) => v !== null && v !== undefined)
      .map((v) => String(v).trim())
      .filter((v) => v.length > 0);

    return [...new Set(skus)];
  }

  async function executeAutomation(skus, imageFile) {
    const menuButtons = [
      { text: "商品和价格", ruText: "Товары и цены" },
      { text: "质量监督", ruText: "Контроль качества" },
      { text: "卖家使用我的品牌", ruText: "Продавцы используют мой бренд" },
    ];

    setStatus("🎯 正在导航菜单...", "#3b82f6");

    for (let i = 0; i < menuButtons.length; i++) {
      const item = menuButtons[i];
      setStatus(
        `🎯 正在导航菜单...\n第 ${i + 1}/${menuButtons.length} 步：${item.text}`,
        "#3b82f6",
      );
      await clickMenuButton(item.text, item.ruText, CONFIG.menuRetryCount);
    }

    setStatus(`✅ 菜单导航完成，开始处理 ${skus.length} 个 SKU...`, "#059669");

    for (let i = 0; i < skus.length; i++) {
      const sku = skus[i];
      setStatus(`📦 正在处理 SKU ${i + 1}/${skus.length}：${sku}`, "#3b82f6");

      await processSingleSku(sku, imageFile);

      setStatus(`✅ SKU ${i + 1}/${skus.length} 处理完成：${sku}`, "#059669");
      await sleep(1200);
    }
  }

  async function findDirectFileInputWithRetry(maxRetries = 2) {
    const xpaths = [`//input[@type='file']`];

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      const found = await findElementByXpaths(xpaths, 2000);
      if (found) {
        return found;
      }
      await sleep(800);
    }

    return null;
  }
  async function findElementByXpaths(selectors, timeout = 4000) {
    const start = Date.now();

    while (Date.now() - start < timeout) {
      for (const selector of selectors) {
        try {
          const node = document.evaluate(
            selector,
            document,
            null,
            XPathResult.FIRST_ORDERED_NODE_TYPE,
            null,
          ).singleNodeValue;

          if (node) {
            return node;
          }
        } catch (error) {
          console.warn(`XPath 执行失败: ${selector}`, error);
        }
      }

      await sleep(CONFIG.generalPollIntervalMs);
    }

    return null;
  }

  async function pressEnter(target) {
    if (!target) {
      target = document.activeElement || document.body;
    }

    if (target.focus) {
      target.focus();
      await sleep(100);
    }

    target.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Enter",
        code: "Enter",
        keyCode: 13,
        which: 13,
        bubbles: true,
        cancelable: true,
      }),
    );

    target.dispatchEvent(
      new KeyboardEvent("keypress", {
        key: "Enter",
        code: "Enter",
        keyCode: 13,
        which: 13,
        bubbles: true,
        cancelable: true,
      }),
    );

    target.dispatchEvent(
      new KeyboardEvent("keyup", {
        key: "Enter",
        code: "Enter",
        keyCode: 13,
        which: 13,
        bubbles: true,
        cancelable: true,
      }),
    );
  }

  async function processSingleSku(sku, imageFile) {
    const skuInput = await findSkuInputWithRetry();
    await setInputValue(skuInput, sku);

    // 第一次回车：提交 SKU
    await pressEnter(skuInput);
    await sleep(2000);

    await waitForSearchResult(sku);

    const fileInput = await findFileInputWithRetry();
    await uploadFileToInput(fileInput, imageFile);

    // 第二次回车：提交图片
    const sendBtn = await waitForSendButtonEnabled(fileInput);
    safeClick(sendBtn);
    await sleep(2000);

    await waitForUploadFinished();
  }

  async function clickMenuButton(text, ruText = null, maxRetries = 3) {
    const selectors = buildTextXpaths(text, ruText);

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      setStatus(
        `🎯 正在查找菜单：${text}\n尝试 ${attempt}/${maxRetries} 次...`,
        "#3b82f6",
      );

      const button = await findVisibleElementByXpaths(
        selectors,
        CONFIG.menuFindTimeoutMs,
      );

      if (button) {
        try {
          await ensureElementClickable(button);

          setStatus(
            `🖱️ 已找到菜单：${text}\n正在点击，第 ${attempt}/${maxRetries} 次...`,
            "#3b82f6",
          );
          safeClick(button);

          await sleep(CONFIG.afterClickWaitMs);
          return true;
        } catch (error) {
          console.warn(`点击菜单失败 [${text}] 第 ${attempt} 次:`, error);
        }
      }

      if (attempt < maxRetries) {
        await sleep(CONFIG.menuRetryGapMs);
      }
    }

    throw new Error(`找不到或无法点击菜单按钮: ${text}`);
  }
  async function findSkuInputWithRetry(maxRetries = 3) {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      const found = await findVisibleElementByXpaths([`//textarea`], 2500);
      if (found) return found;
      await sleep(1000);
    }

    throw new Error("未找到 SKU 输入框 textarea");
  }

  async function findSearchButtonWithRetry(maxRetries = 3) {
    const xpaths = [
      `//button[contains(normalize-space(.), '搜索')]`,
      `//button[contains(normalize-space(.), '查询')]`,
      `//button[contains(normalize-space(.), '查找')]`,
      `//button[contains(normalize-space(.), 'Найти')]`,
      `//button[contains(normalize-space(.), 'Поиск')]`,
      `//button[contains(normalize-space(.), 'Search')]`,
      `//span[contains(normalize-space(.), '搜索')]/ancestor::button[1]`,
      `//span[contains(normalize-space(.), '查询')]/ancestor::button[1]`,
      `//span[contains(normalize-space(.), 'Найти')]/ancestor::button[1]`,
    ];

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      const found = await findVisibleElementByXpaths(xpaths, 2500);
      if (found) return found;
      await sleep(800);
    }

    return null;
  }

  async function waitForSendButtonEnabled(fileInput, timeout = 15000) {

    const start = Date.now();
  
    while (Date.now() - start < timeout) {
  
      const container = fileInput.closest("div");
  
      if (container) {
  
        const buttons = container.querySelectorAll("button");
  
        const sendBtn = buttons[buttons.length - 1];
  
        if (sendBtn) {
  
          const disabled =
            sendBtn.disabled ||
            sendBtn.getAttribute("disabled") !== null ||
            sendBtn.getAttribute("aria-disabled") === "true";
  
          if (!disabled) {
            return sendBtn;
          }
        }
      }
  
      await sleep(300);
    }
  
    throw new Error("等待发送按钮可用超时");
  }
  async function waitForSearchResult(
    sku,
    timeout = CONFIG.searchResultTimeoutMs
  ) {
    const start = Date.now();
  
    while (Date.now() - start < timeout) {
      const fileInput = await findElementByXpaths(
        [`//input[@type='file']`],
        800
      );
      if (fileInput) {
        return true;
      }
  
      const bodyText = document.body.innerText || "";
      if (bodyText.includes(sku)) {
        return true;
      }
  
      await sleep(500);
    }
  
    throw new Error(`等待 SKU 查询结果超时: ${sku}`);
  }

  async function findUploadEntryButtonWithRetry(maxRetries = 3) {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      const found = await tryFindUploadEntryButtonOnce();
      if (found) return found;
      await sleep(1000);
    }

    throw new Error("未找到上传图片入口按钮");
  }

  async function tryFindUploadEntryButtonOnce() {
    const xpaths = [
      `//button[contains(normalize-space(.), '上传')]`,
      `//button[contains(normalize-space(.), '上传图片')]`,
      `//button[contains(normalize-space(.), '添加图片')]`,
      `//button[contains(normalize-space(.), 'Upload')]`,
      `//button[contains(normalize-space(.), 'Add image')]`,
      `//button[contains(normalize-space(.), 'Загрузить')]`,
      `//button[contains(normalize-space(.), 'Добавить фото')]`,
      `//span[contains(normalize-space(.), '上传')]/ancestor::button[1]`,
      `//span[contains(normalize-space(.), '上传图片')]/ancestor::button[1]`,
      `//span[contains(normalize-space(.), '添加图片')]/ancestor::button[1]`,
      `//span[contains(normalize-space(.), 'Загрузить')]/ancestor::button[1]`,
      `//span[contains(normalize-space(.), 'Добавить фото')]/ancestor::button[1]`,
    ];

    return await findVisibleElementByXpaths(xpaths, 2000);
  }

  async function findFileInputWithRetry(maxRetries = 3) {
    const xpaths = [
      `//input[@type='file' and contains(@accept, 'image')]`,
      `//input[@type='file']`,
    ];

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      const found = await findElementByXpaths(xpaths, 2500);
      if (found) {
        return found;
      }

      await sleep(1000);
    }

    throw new Error("未找到图片上传 input[type='file']");
  }

  async function uploadFileToInput(fileInput, file) {
    if (!fileInput) {
      throw new Error("文件输入框不存在");
    }

    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    fileInput.files = dataTransfer.files;

    fileInput.dispatchEvent(new Event("input", { bubbles: true }));
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));

    await sleep(1500);
  }

  async function waitForUploadFinished(
    timeout = CONFIG.uploadFinishedTimeoutMs,
  ) {
    const successTexts = [
      "上传成功",
      "已上传",
      "上传完成",
      "успешно",
      "загружено",
      "готово",
      "success",
    ];

    const errorTexts = ["上传失败", "失败", "error", "ошибка"];

    const start = Date.now();

    while (Date.now() - start < timeout) {
      const bodyText = (document.body.innerText || "").toLowerCase();

      for (const text of errorTexts) {
        if (bodyText.includes(text.toLowerCase())) {
          throw new Error("检测到上传失败提示");
        }
      }

      for (const text of successTexts) {
        if (bodyText.includes(text.toLowerCase())) {
          return true;
        }
      }

      await sleep(800);
    }

    return true;
  }

  async function setInputValue(input, value) {
    if (!input) {
      throw new Error("输入框不存在");
    }

    input.focus();
    await sleep(200);

    const tagName = input.tagName.toLowerCase();

    const setNativeValue = (val) => {
      if (tagName === "textarea") {
        const nativeTextAreaSetter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype,
          "value",
        )?.set;

        if (nativeTextAreaSetter) {
          nativeTextAreaSetter.call(input, val);
        } else {
          input.value = val;
        }
      } else {
        const nativeInputSetter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,
          "value",
        )?.set;

        if (nativeInputSetter) {
          nativeInputSetter.call(input, val);
        } else {
          input.value = val;
        }
      }
    };

    setNativeValue("");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await sleep(150);

    setNativeValue(value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));

    await sleep(300);
  }

  function buildTextXpaths(text, ruText = null) {
    const values = [text];
    if (ruText) values.push(ruText);

    const selectors = [];

    for (const value of values) {
      const safeValue = escapeXpathText(value);

      selectors.push(`//span[contains(normalize-space(.), ${safeValue})]`);
      selectors.push(`//span[normalize-space(text())=${safeValue}]`);
      selectors.push(`//button[contains(normalize-space(.), ${safeValue})]`);
      selectors.push(`//a[contains(normalize-space(.), ${safeValue})]`);
      selectors.push(`//*[contains(normalize-space(.), ${safeValue})]`);
    }

    return selectors;
  }

  async function findVisibleElementByXpaths(selectors, timeout = 4000) {
    const start = Date.now();

    while (Date.now() - start < timeout) {
      for (const selector of selectors) {
        try {
          const node = document.evaluate(
            selector,
            document,
            null,
            XPathResult.FIRST_ORDERED_NODE_TYPE,
            null,
          ).singleNodeValue;

          if (node && isElementVisible(node)) {
            return node;
          }
        } catch (error) {
          console.warn(`XPath 执行失败: ${selector}`, error);
        }
      }

      await sleep(CONFIG.generalPollIntervalMs);
    }

    return null;
  }

  async function ensureElementClickable(el) {
    if (!el) {
      throw new Error("目标元素为空");
    }

    if (typeof el.scrollIntoView === "function") {
      el.scrollIntoView({
        behavior: "smooth",
        block: "center",
        inline: "center",
      });
    }

    await sleep(CONFIG.clickAfterScrollDelayMs);

    if (!isElementVisible(el)) {
      throw new Error("目标元素不可见");
    }
  }

  function safeClick(el) {
    if (!el) {
      throw new Error("无法点击空元素");
    }

    if (typeof el.click === "function") {
      el.click();
      return;
    }

    el.dispatchEvent(
      new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        view: window,
      }),
    );
  }

  function isElementVisible(el) {
    if (!el || !(el instanceof Element)) {
      return false;
    }

    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();

    return !(
      style.display === "none" ||
      style.visibility === "hidden" ||
      style.opacity === "0" ||
      rect.width === 0 ||
      rect.height === 0 ||
      el.offsetParent === null
    );
  }

  function escapeXpathText(text) {
    if (!text.includes("'")) {
      return `'${text}'`;
    }

    if (!text.includes('"')) {
      return `"${text}"`;
    }

    const parts = text.split("'");
    return `concat('${parts.join(`', "'", '`)}')`;
  }

  async function waitFor(selector, timeout = CONFIG.waitTimeoutMs) {
    const start = Date.now();

    while (Date.now() - start < timeout) {
      const el = document.querySelector(selector);
      if (el) return el;
      await sleep(CONFIG.generalPollIntervalMs);
    }

    throw new Error(`等待 ${selector} 超时`);
  }

  async function waitForText(text, timeout = CONFIG.waitTimeoutMs) {
    const start = Date.now();
    const safeText = escapeXpathText(text);

    while (Date.now() - start < timeout) {
      const result = document.evaluate(
        `//*[contains(normalize-space(.), ${safeText})]`,
        document,
        null,
        XPathResult.FIRST_ORDERED_NODE_TYPE,
        null,
      ).singleNodeValue;

      if (result && isElementVisible(result)) {
        return result;
      }

      await sleep(CONFIG.textPollIntervalMs);
    }

    throw new Error(`找不到包含 "${text}" 的元素`);
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function getErrorMessage(error) {
    if (error instanceof Error && error.message) {
      return error.message;
    }
    return String(error);
  }

  function setStatus(message, color = "#6b7280") {
    const statusDiv = document.getElementById(CONFIG.statusId);
    if (!statusDiv) return;
    statusDiv.textContent = message;
    statusDiv.style.color = color;
  }
})();
