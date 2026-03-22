const status = document.getElementById('status');

document.getElementById('start').onclick = async () => {
  try {
    status.textContent = '正在跳转到Ozon卖家后台...';

    // 打开Ozon卖家后台页面
    const tab = await chrome.tabs.create({
      url: 'https://seller.ozon.ru/app/messenger?channel=SCRM'
    });

    status.textContent = '已打开Ozon卖家后台，请在页面内完成后续操作。';

    // 等待页面加载完成
    await new Promise(resolve => setTimeout(resolve, 3000));

    // 注入自动化脚本
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ['content.js']
    });

  } catch (error) {
    console.error('跳转失败:', error);
    status.textContent = `出错: ${error.message}`;
  }
};