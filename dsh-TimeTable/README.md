# dsh-TimeTable

> 把「现在这个任务」排到下一个 DeepSeek 谷时再跑，省一半以上的 token 钱。

`dsh-TimeTable` 是给 [DeepSeek Harness](https://github.com/) 用的技能（skill）：一句话把当前任务挂成**会话级定时任务**，时间落在下一个 **DeepSeek 价格谷时起点**；到点自动继续执行并把结果汇报回来。如果发起时已经处于谷时，它不会让你白等——直接执行。

## 峰谷规则（北京时间 Asia/Shanghai）

| 时段 | 判定 |
|---|---|
| 周一至周五 09:00–12:00 | 🔴 高峰 |
| 周一至周五 14:00–18:00 | 🔴 高峰 |
| 工作日 00:00–09:00、12:00–14:00、18:00–24:00 | 🟢 谷时 |
| 周六、周日全天 | 🟢 谷时 |
| 法定节假日全天（按国务院放假通知） | 🟢 谷时 |

边界：09:00:00 起算高峰，12:00:00 起算谷时，14:00:00 起算高峰，18:00:00 起算谷时。

## 排期规则

| 发起时刻 | 动作 |
|---|---|
| 工作日 09:00–12:00 | 排到同日 **12:00** |
| 工作日 14:00–18:00 | 排到同日 **18:00** |
| 已是谷时（早晚、午间、周末、节假日） | **立即执行**，不建定时任务 |
| 用户坚持「谷时也要排下个起点」 | `--wait-next`，等过下一段高峰后执行 |

两个刻意的设计取舍：

- **已在谷时不排队**：谷时已经在生效，再排就是空等。避免出现「周五 19:00 呼叫 → 被排到下周一 12:00」这种反直觉结果。
- **调休上班的周六/周日仍算谷时**：规则写的是「周末全天」谷时，不因调休上班变成高峰。要改就动脚本里的 `classify()` + `workdays` 清单。

## 安装

技能放在 DSH 的全局技能目录，所有工作区都能调用：Windows `%USERPROFILE%\.dsh\skills\`，macOS/Linux `~/.dsh/skills/`。

### 方式 A：git clone（推荐）

```bash
git clone https://github.com/1483193713/dsh-TimeTable.git ~/.dsh/skills/timetable
```

### 方式 B：下载 zip

下载本仓库 zip，解压后把整层目录重命名为 `timetable`，放到 `~/.dsh/skills/timetable`。

### 方式 C：手动复制

把 `SKILL.md`、`scripts/`、`references/` 三样放进 `~/.dsh/skills/timetable/` 即可（`README.md`、`LICENSE`、`.github/` 可以不放）。

装好后新开一个会话，技能列表里出现 `timetable` 就生效了。

## 使用

在对话里直接说：

```
把这个任务设成定时任务，排到下一个谷时
排到谷时再跑
TimeTable：帮我生成一份 30 页的测试报告
```

Agent 会加载 `timetable` 技能，算出目标时刻，调用 `schedule_create` 建立定时提醒；到点后会话收到提醒，继续把任务做完。

### 也可以单独跑脚本

脚本不依赖 DSH，纯标准库，任何 Python 3.9+ 都能跑：

```bash
python3 scripts/next_offpeak.py                                  # 现在算
python3 scripts/next_offpeak.py --now 2026-11-02T15:10:00+08:00   # 指定基准时间
python3 scripts/next_offpeak.py --json                            # 机器可读
python3 scripts/next_offpeak.py --wait-next                       # 谷时也强制排队
python3 scripts/next_offpeak.py --selftest                        # 回归测试
```

高峰期（周一 15:10）的输出：

```
TimeTable · 北京时间 2026-11-02 15:10（周一）
当前状态：高峰（工作日下午高峰 14:00–18:00）
动作：创建定时任务（schedule_create）
目标时刻：2026-11-02 18:00（周一），距现在 2 小时 50 分
  at = {"date": "2026-11-02", "time": "18:00:00", "time_zone": "Asia/Shanghai"}
依据：当前处于工作日下午高峰 14:00–18:00，谷时起点 = 本段高峰结束时刻
```

谷时（周一 20:00）的输出：

```
TimeTable · 北京时间 2026-11-02 20:00（周一）
当前状态：谷时（工作日谷间（00:00–09:00 / 12:00–14:00 / 18:00–24:00））
动作：立即执行（run_now），不要建定时任务
起点：现在 + 1 分钟（2026-11-02 20:01（周一））
依据：当前已是谷时（工作日谷间（00:00–09:00 / 12:00–14:00 / 18:00–24:00）），谷时已生效，立即执行，无需空等
```

## 目录结构

```
.
├── SKILL.md                    # 技能定义：规则、排期逻辑、schedule_create 参数写法
├── scripts/
│   └── next_offpeak.py         # 谷时起点计算（含 --selftest 15 条回归用例）
├── references/
│   └── holidays.json           # 法定节假日「放假日期」表（2025–2026 已内置，2027 待发布）
└── .github/workflows/selftest.yml
```

## 节假日数据维护

`references/holidays.json` 只登记**放假**日期，不登记调休上班日（周末已按谷时算）。某个年份的 `ranges` 为 `[]` 表示国务院通知还没发布，脚本遇到该年份会打印 `WARN` 并提示先联网核对，不会静默猜错。

每年 11 月前后国务院办公厅发布次年安排后，把区间补进去即可，不用改代码：

```json
"2027": [
  ["2027-01-01", "2027-01-03"],
  ["2027-02-05", "2027-02-13"]
]
```

改完跑一遍 `--selftest`，再补一条对应的用例更稳妥。

## FAQ

**Q：为什么我在晚上发起，它没有排到第二天？**
你已经在谷时了，谷时正在生效，直接跑就是谷时价格，排队只会白等。

**Q：定时任务换个会话还在吗？**
`schedule_create` 是会话级的：到点把 prompt 投回**当前会话**继续跑。换会话、关会话都不会在别的会话里执行。

**Q：能精确到 12:00:00 吗？**
能。目标时刻就是整点，脚本不会给你挪到 11:59 或 12:05 去「避让」。

**Q：Windows 上跑会不会因为缺时区数据报错？**
不会。脚本优先用 `zoneinfo` 的 `Asia/Shanghai`；Windows 缺 `tzdata` 包时自动退回固定 `+08:00`（中国无夏令时，结果一致）。

**Q：非 DSH 环境能用吗？**
脚本本身可以（它`--json`输出目标时刻）；「到点自动继续执行」依赖 DSH 的 `schedule_create`。

## 开发

- 纯标准库，无第三方依赖；Python 3.9+
- 回归测试：`python3 scripts/next_offpeak.py --selftest`（CI 在 push / PR 时自动跑）
- 改动规则后请同步更新 `SKILL.md` 的判定表和 `CASES` 用例

## 推送到 GitHub

```bash
git init -b main
git add .
git commit -m "feat: TimeTable skill v1.0.0"
git remote add origin https://github.com/1483193713/dsh-TimeTable.git
git push -u origin main
```

仓库名建议就叫 `dsh-TimeTable`，README 里已经按这个名字写好了安装命令。

## 更新日志

- **v1.0.0**（2026-11-02）：首个版本。峰谷判定、节假日表、会话级定时排期、`--selftest` 15 条用例。

## License

[MIT](LICENSE) © 2026 1483193713
