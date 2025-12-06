# 🚀 AlphaPilot - 工程师的个人美股投资驾驶舱

> Automated Wealth Management Dashboard | **Keep Calm & DCA On**

## 📦 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate  # macOS/Linux
# 或
.\venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 运行应用

```bash
source venv/bin/activate
streamlit run app.py --server.port 8501 --server.headless true
```

打开浏览器访问：http://localhost:8501

---

## 🎯 功能模块

### 模块 A: 宏观天眼 (Macro Dashboard)
- **CNN 恐慌贪婪指数**: 0-100 分，< 25 极度恐惧（买入良机），> 75 极度贪婪（风险警示）
- **VIX 恐慌指数**: > 30 可能是市场底部
- **美债 10 年期收益率**: 高收益率压制成长股估值

### 模块 B: 核心资产体检表 (Asset Health)
跟踪 VOO、QQQ、SMH、TLT 的：
- 当前价格
- RSI (14) 指标
- 年线 (MA200) 乖离率
- **AlphaPilot 信号**：🟢 极佳买点 / ⚪️ 正常定投 / 🟠 估值过高 / 🔴 严重超买

### 模块 C: 深度技术分析
- K线 + MA20 (短期趋势) + MA200 (长期趋势)
- RSI 走势图 + 30/70 阈值线

---

## 📊 AlphaPilot 信号逻辑

| 条件 | 信号 | 建议 |
|------|------|------|
| 跌破年线 + RSI < 35 | 🟢 极佳买点 (加倍) | 加倍定投 |
| RSI < 30 | 🟢 超卖反弹 (买入) | 正常买入 |
| RSI > 75 | 🔴 严重超买 (警惕) | 暂停买入 |
| 高于年线 20%+ | 🟠 估值过高 (持有) | 减少定投 |
| 其他 | ⚪️ 正常定投 | 正常定投 |

---

## 🔄 日常使用流程 (SOP)

### 每周/每月发薪日

1. 打开 AlphaPilot 网页
2. 查看顶部 **CNN 指数** 和 **VIX**
   - 恐惧状态 → 准备多投一点
3. 查看 **QQQ/VOO** 的状态信号
   - `⚪️ 正常定投` → 买入 $2000
   - `🟢 极佳买点` → 买入 $4000（动用储备）
   - `🟠 估值过高` → 买入 $1000 或暂停
4. 在 Charles Schwab App 下单
5. **不要频繁看盘**，去钻研自动驾驶算法 🚗

---

## 🚀 部署到 Streamlit Cloud

1. 将代码推送到 GitHub 私有仓库
2. 访问 [share.streamlit.io](https://share.streamlit.io)
3. 连接你的 GitHub 仓库
4. 选择 `app.py` 作为入口文件
5. 点击 Deploy！

---

## ⚠️ 免责声明

本工具仅供学习和参考，不构成投资建议。投资有风险，入市需谨慎。

---

## 📝 License

MIT License


