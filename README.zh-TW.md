[English](README.md) | 繁體中文

# LoopForge

一個 AI agent loop 的設計教練（design coach）——支援 Claude Code、Codex，或任何
agent runtime（代理執行環境）。它會透過六個階段訪談使用者——goal（目標）、
verification（驗證）、council（協作陣容）、gates and caps（關卡與上限）、
preview（預覽）、emit（產出）——針對每個回答依照 rubric（評分準則）提出批評，
並產出一份 spec，以及一份供 AI agent loop 使用的 orchestrator（協調者）操作
手冊，讓這個迴圈能夠自行建置、檢查並修正自己的成果。

LoopForge 只負責設計，不負責執行：它從不啟動迴圈——產出（emit）之後，何時開啟第一次迭代（iteration 1）由人類決定。

## Install

**Claude Code** —— clone 到你的 skills 目錄，然後執行 slash command：

```bash
git clone https://github.com/kennethlaw325/loopforge.git ~/.claude/skills/loopforge
```
```
/loopforge ./my-loop
```

**Codex** —— clone 到全域（global）skills 目錄（或者專案內的 `.agents/skills/`，
做一份限定專案範圍的副本），然後直接叫它的名字：

```bash
git clone https://github.com/kennethlaw325/loopforge.git ~/.agents/skills/loopforge
```
```
Use the loopforge skill to design a loop in ./my-loop
```

**其他任何 agent runtime（代理執行環境）** —— clone 到任何地方，把 `SKILL.md`
當作 system prompt 或任務簡報餵給你的 agent，讓它在走到每個階段時自己讀取
`references/*.md`。`scripts/loopforge.py` 是一支單純的 CLI：它完全不需要任何
agent，人類也可以照著 `RUN.md` 手動驅動整個迴圈。

`--fast` 會在某個階段的回答已經夠紮實時直接採用，而不是逐一批評每個階段。

**需求：** Python 3.11+（Windows 用 `py -3`，macOS/Linux 用 `python3`），以及用來
讀取 `SPEC.yaml` 的 PyYAML（`py -3 -m pip install PyYAML`）。這是唯一的依賴套件——
除此之外，編譯器（compiler）、cap 檢查器與儀表板渲染器都只用到標準函式庫
（stdlib）。

## 它會產出的檔案

| 檔案 | 代表意義 | 由誰寫入 |
|---|---|---|
| `SPEC.yaml` | **要建置什麼**，以及會如何被評判 | 你，透過訪談過程 |
| `PLAN.md` | **為什麼**這個迴圈會長成這個樣子 | 編譯器 |
| `RUN.md` | **如何**執行它——orchestrator 的操作手冊 | 編譯器 |
| `implementation-notes.md` | 建置過程中實際發生了什麼 | builder（建置者），每次迭代 |
| `loop.resolved.json` | 機器可讀的 spec | 編譯器 |
| `loop-state.json` | 迭代次數、判決結果、花費 | orchestrator |
| `loop.html` | 單頁儀表板 | `render`，每次迭代 |

Agent 負責編輯 markdown 與 JSON。人類負責閱讀渲染後的 HTML。

## Quickstart

1. **Design（設計）。** 呼叫這個 skill（`/loopforge ./my-loop`，或者你的 runtime
   載入它的方式）走過六個階段並寫出 `SPEC.yaml`。
2. **Compile（編譯）。** `py -3 scripts/loopforge.py compile ./my-loop/SPEC.yaml` 會產出
   `loop.resolved.json`、`PLAN.md` 與 `RUN.md`。它會拒絕任何讓迴圈自行為自己的成果簽核、
   讓 reviewer（審閱者）發出 verdict（判決）、讓 builder 為自己打分，或是缺少某個 cap
   （上限）設定的 spec。
3. **Human go（人類放行）。** 閱讀預覽內容。在使用者同意之前，什麼都不會執行。
4. **Run（執行）。** 一個 agent session（或者一個人）會依照 `RUN.md` 作為這個迴圈的
   orchestrator。每次迭代它會執行 `loopforge.py check`（讀取檔案來判斷某個 cap
   是否還允許再跑一輪）、生成（spawn）一個全新的 builder agent、自行執行
   programmatic（程式化）判準、為腳本無法衡量的部分生成一個全新的 judge agent，
   並把 verdict 附加到 `loop-state.json`。「Fresh agent（全新的 agent）」指的是
   你的 runtime 提供的任何形式：一個 subagent、一個新的 session，或是一個獨立
   的 process——真正的要求是乾淨的 context，而不是某個特定功能。
5. **Render（渲染）。** `loopforge.py render ./my-loop` 會重新產生 `loop.html`：
   進度、verdict 歷史、判準檢查清單，以及釘選在頂端的 builder 開放式問題。

最後一道 gate（關卡）永遠是人類。builder 可能會誤讀 spec，而 same-family（同家族）的
judge 也可能用同樣的方式誤讀——那道 gate 正是讓人抓出問題的地方。

## Security model（安全模型）

LoopForge 是一個單一操作者（single-operator）工具：spec 由使用者自己寫、迴圈由
使用者自己跑，它碰到的每一樣東西都是以使用者自己的身分在執行。

- **`SPEC.yaml` 是可執行的設定。** 它的 `check` 指令會以使用者自己的權限執行。
  審查一份不是自己寫的 spec，要用審查一份 Makefile 或 CI 設定檔的心態，先看
  過內容再執行。
- **`loop-state.json` 與 `implementation-notes.md` 都是普通檔案。** 它們是這個
  迴圈的記憶，不是一份防竄改的稽核紀錄——任何對這個目錄有寫入權限的東西都能
  編輯它們。
- **預設情況下什麼都不會離開使用者的機器。** 預設的 judge 是使用者自己 session
  裡的一個 subagent。選用的外部 judge 會把產出物送到第三方 API；這是選擇性
  加入（opt-in）的功能，privacy（隱私）合約（遮蔽、內容清理、第一次傳送前
  要取得同意）只有在使用者啟用它之後才會生效。

## Tests

```bash
py -3 scripts/test_loopforge.py
```
