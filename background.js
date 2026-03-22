// 可选：保留自动注入功能，当用户直接访问Ozon卖家后台时自动注入脚本
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
    if (changeInfo.status !== 'complete') return;
    if (!tab.url?.includes('seller.ozon.ru')) return;

    try {
        // 检查是否已注入过脚本
        const existingScript = await chrome.scripting.executeScript({
            target: { tabId },
            function: () => !!window.__ozonKickAutomationInjected
        });

        if (existingScript[0]?.result) {
            return;
        }

        // 注入核心自动化脚本
        await chrome.scripting.executeScript({
            target: { tabId },
            files: ['content.js']
        });

        // 标记已注入
        await chrome.scripting.executeScript({
            target: { tabId },
            function: () => window.__ozonKickAutomationInjected = true
        });

        console.log('Ozon踢跟助手脚本已自动注入');

    } catch (err) {
        console.error('注入失败', err);
    }
});