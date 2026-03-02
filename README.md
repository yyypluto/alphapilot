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

### 2. 配置 API Keys

```bash
# 复制配置模板
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# 编辑配置文件，填入你的 API Keys
vim .streamlit/secrets.toml
```

**需要配置的 API Keys:**
- `SUPABASE_URL` / `SUPABASE_KEY`: 数据库（可选）
- `POLYGON_API_KEY`: 期权数据（**V7.0 新增**）
  - 获取地址: https://polygon.io/dashboard/api-keys
  - 免费账户: 每分钟 5 次调用

### 3. 运行应用

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

### 🆕 模块 D: Option Alpha Lab (V7.0 新增)
智能期权选筹模块，根据市场状态自动推荐最佳期权策略：

| 市场状态 | 推荐策略 | 说明 |
|---------|---------|------|
| **State 0** (进攻) | 🚀 LEAPS Call | 深实值长期看涨期权，替代 QLD 获得杠杆敞口 |
| **State 1** (防御) | 🛡️ 持有 QQQ | 降低杠杆，规避损耗 |
| **State 2** (撤退) | 💰 Sell Put (CSP) | 卖出虚值看跌期权收租，等待抄底 |

**核心筛选逻辑：**
- LEAPS Call: Delta 0.80-0.90，到期 > 365 天，深实值
- CSP: Delta -0.20~-0.30，到期 30-45 天，OTM 收租

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
4. **查看侧边栏 Option Alpha Lab** (V7.0 新功能)
   - State 0 → 点击"扫描 LEAPS"获取替代 QLD 的期权
   - State 2 → 点击"扫描 CSP"获取收租期权建议
5. 在 Charles Schwab App 下单
6. **不要频繁看盘**，去钻研自动驾驶算法 🚗

---

## 🚀 部署到 Streamlit Cloud

1. 将代码推送到 GitHub 私有仓库
2. 访问 [share.streamlit.io](https://share.streamlit.io)
3. 连接你的 GitHub 仓库
4. 选择 `app.py` 作为入口文件
5. 在 Secrets 中配置 `POLYGON_API_KEY` 等
6. 点击 Deploy！

---

## ⚠️ 免责声明

本工具仅供学习和参考，不构成投资建议。投资有风险，入市需谨慎。

---

## 📝 License

MIT License


