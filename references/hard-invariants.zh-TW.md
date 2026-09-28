> 此為 `hard-invariants.md` 的中文對照版，僅供閱讀參考；skill 實際載入與生效的是英文版原始檔案。

# Hard Invariants（硬性不變條件）—— 整合後的錯題簿登記表

彙整自四套實際上線的 agent harness：一個分階段的設計迴圈、一個無人值守的過夜
agent、一個長時間運行的任務排程器，以及一個多階段的內容 pipeline。以下每一條
都是真的在某個地方出過事、也真的花掉真實時間的 bug。方括號〔...〕裡的說明，
就是這個 bug 實際發作時的樣子。

**如何使用（Stage 2 與 Stage 4）：** 逐一走過適用的段落。每一條 invariant
（不變條件）要嘛在 `SPEC.yaml` 裡變成一條具體的 check／spec 規則，要嘛就在
`invariants:` 區塊裡寫下一條 `status: waived`（已豁免）的紀錄並附上理由。
保持沉默不算豁免。標了 ✅ 的條目已經由內附的 adapter／編譯器強制執行——
直接倚賴即可，不必再重新產生一次。

## J —— Judge 與 verdict 的輸入輸出

- **J1 · Judge 傳輸必須位元組透明。** ✅ 內附的 adapter 會以 bytes + UTF-8 的方式
  讀取 stdin，並拒絕亂碼（連續出現 `????` → warning=mojibake_input）。spec 這邊：
  把外部 judge 的 invoke 固定成一條位元組透明的 pipe；絕不能是一個會重新編碼的
  shell。〔一個 judge 對整段全是 `??` 的文字打分，並對這堆垃圾給出一個信心滿滿
  的 verdict〕
- **J2 · Verdict 是一筆有型別的紀錄。** ✅ adapter：`revise`（要求修訂）卻沒有任何
  一條可執行的 blocking issue → 自動重問一次，再不行就標記
  warning=verdict_inconsistent。〔verdict 欄位寫著 revise，內文卻說一切都可以
  接受，confidence 還寫 1.0〕
- **J3 · 每個問題都要指出對應的 rubric。** ✅ adapter 的 system prompt：每一條
  blocking issue 開頭都要標明 `[它違反的那條判準]`；指不出來的就只能算 notes
  裡的建議（advisory）。〔一個 plan judge 抱怨某個排序方式，結果那個排序方式
  正是 rubric 本身要求的，白白燒掉了整個 revision 額度〕
- **J4 · 依故障來源計算 revision 額度。** `max_revisions` 只計算 EXECUTOR
  （執行者）的故障。judge／傳輸層的故障（任何帶 `warning` 的 verdict）都是
  免費的重新查詢，受限於另一個獨立的 judge_fault_cap（約 3 次），超過就上報
  給人類。人類 checkpoint 造成的重做會開啟一個**新的**迭代——絕不會消耗 gate
  的額度。狀態要以 `{round, fault_source: executor|judge|transport|human,
  consumed}` 的格式記錄每一輪。〔人類自己給的意見回饋，把交付額度 3/3 全部
  耗光了〕
- **J5 · 單行 JSON 結果合約，雙邊都要強制遵守。** 每一次 executor 的結束
  （成功以及每一種有型別的失敗）都只能吐出恰好一行非空的 JSON；接收端要用
  「從結尾開始掃描、以 ok 為錨點」的方式解析；自由文字的 argv 值要用
  `--flag=value` 的形式傳遞（開頭一個減號不算是 argparse 的 SystemExit）。
  〔輸出用了 indent=2，接收端卻是單行解析器：本來成功的執行全部被回報成
  失敗〕
- **J6 · 解析失敗要是一個有型別的終端狀態。** 沒通過 schema 驗證的 executor
  輸出 = `parse_error`（絕不能算成功）；把原始 stdout 隔離保存；並且要算進
  連續失敗警報的計數裡。〔一個 fallback 讓解析失敗的執行也當作成功往下游
  流動〕
- **J7 · 驗證用的 harness 本身，在被煙霧測試（smoke-tested）之前都不可信。**
  只有在實際執行過它、並且從真實的 stdout 裡解析出 `N pass / 0 fail` 之後，
  才能說「驗證通過」。禁止把 VCS 指令的 exit code 當作 pass/fail 訊號來用
  （hook 會污染它）。針對替代品（stand-in）寫成的 harness，在 commit 之前
  還需要：(a) 由一位新的讀者，逐條斷言（assertion）對照它所引用的 SPEC
  行覆核——oracle 與 stand-in 共用、但 SPEC 沒有寫明的規則，要寫進 harness
  的 README 作為詮釋（interpretation），否則就是耦合（coupling）；(b) 每一個
  從真實設定檔（real config）推導出 watched／root set 的腳本，都要跑一次
  真實設定的 dry run，把印出來的 scope 對照預期清單核對。〔一次迭代裡出現
  3 個假的 FAIL，全都來自一個 post-checkout hook；對著替代品跑出的綠色
  selftest 隱藏了六個 spec 耦合漏洞；只在 sandbox 裡做的 smoke test，隱藏了
  一個 scope 遠比預期寬的 watcher〕

## G —— Gate 與計畫設計

- **G1 · 一個被記錄下來的風險，不等於已經被緩解。** 每一列 Risks（風險）
  都必須帶有 `mitigating_check_id`（指向一條真實存在的判準），或是
  `accepted_by_human: <姓名+日期>`；一列空白的風險紀錄本身就是一個機械式的
  blocking issue。〔一週前的舊輸入資料被寫在 Risks 裡，通過了 plan gate，
  然後在人類 checkpoint 引爆〕
- **G2 · Spec 到 plan 的可追溯性。** 每一條 spec 裡的 MUST／整合面向文字，
  都必須對應到某個 plan 任務 ID；一個被標成「optional（可選）」的 plan 任務
  卻對應到一條 MUST 文字，就算失敗。判準涵蓋率不等於 spec 涵蓋率。
  〔一個迴圈判定自己已經 COMPLETE（完成）；人類抓到 spec 寫的是統一入口點，
  plan 卻悄悄出貨了一個獨立入口〕
- **G3 · 每個階段的判準適用性。** 判準要帶有 `applies_when`／`phase` 欄位；
  gate 要自行算出適用的子集；「N/A（不適用）」必須是計算出來的狀態，
  絕不是操作者臨場的即興判斷。〔一份攤平的 8 條判準清單，導致操作者臨場
  自行判斷「這幾條在這裡不適用」〕
- **G4 · 人類 checkpoint 要帶有逾時政策。** `{timeout_min,
  on_timeout: wait | proxy_if_reversible | stop}`；只有在 isolation
  （隔離範圍）等於 branch，而且沒有執行過任何被禁止的副作用時，才允許用
  proxy（代理核准）；proxy 核准要寫成一筆有型別的紀錄。〔一次 AFK（離開）
  60 秒的 proxy 核准是臨場即興決定的——僅僅因為運氣好碰上分支隔離才沒出事〕
  每個 checkpoint 都要同時指明自己的喚醒管道（wake channel）：終端輸入／
  傳給指定 session 的訊息／帶輪詢間隔的檔案輪詢（file poll）；互動式
  orchestrator 不會監看檔案，所以產出的 RUN.md 必須寫明答案要如何送達，而且
  只有在 orchestrator 出現活動時才算送達。〔答案寫進了 checkpoint 檔案，
  卻擱置了 14 分鐘沒人讀取〕
- **G5 · 一個 gate 不能自己寫自己的門檻。** 設定／門檻的雜湊值要斷言在各次
  迭代之間保持不變；要改就必須由人類提交變更。〔一個 budget check 每次花費
  達到 90% 就自動調高自己的上限〕
- **G6 · 宣告的 gate 必須能靠 grep 證實確實有接線。** 每一個 cap／門檻設定
  key 都必須有一個對應的強制執行呼叫點；只存在於 README 裡的 gate，
  compile 時要判定失敗。〔`max_cost_per_run` 存在於設定檔和 README 裡，
  卻沒有任何程式碼真的去讀它〕
- **G7 · 真相重新計算的姊妹判準。** 任何驗證一份生成資料產出物的判準，都要
  搭配一條 `<id>-truth` 姊妹判準，從原始來源重新推導出數字，而不是從
  產出物自己的生成器那裡讀——這樣假綠燈的資料在機制上就不可能發生。
- **G8 · verifier 這一層本身也要被驗證。** race／lock 的修正，需要一個
  barrier 同步、有真正寫入者參與的測試，再加上一次 mutation run
  （還原修正 → 測試變紅 → 恢復 → 再變綠），並記錄在 PR 裡；並行測試不能
  monkeypatch claim 相關的基本操作；跨 repo 的 reviewer 必須先斷言本地
  HEAD 等於 origin，才能提出 blocker。〔一次還原修正之後仍有 306 個測試
  是綠的 = 那個 pin 是假的；一次過期的 checkout 產生了一個假的 blocker〕
- **G9 · 不可逆的行動由一張靜態政策表來控管。** `{action_class → execute |
  report_only}` 在設計時就要決定好；publish／merge／push／檔案搬移／
  正式環境設定變更，預設一律是 report_only（僅回報），並以一份排序過的
  報告作為有型別的輸出。絕不能交給模型在每次迭代時臨場判斷。
- **G10 · Builder 的呼叫方式要被釘住並斷言。** 狀態要記錄每一次派工實際
  使用的 `builder_invoke_actual`；跟 spec 裡 council 條目不一致，就是一筆
  有型別的偏離紀錄 `{spec, actual, justification, approved_by}`，會擋住
  iteration 1。〔spec 釘住了一個特定模型，執行器卻換了一條不同的派工路徑，
  還自我認證說「這是同一個等級」〕

## S —— 狀態完整性

- **S1 · 三種原子性手法，絕不能混為一談。** 原子覆寫 = 唯一的 mkstemp +
  fsync + rename（一個固定不變的 `.tmp` 檔名本身就是一種 race）；
  create-if-absent（不存在才建立）= 在同一個 kernel 操作裡「連內容一起
  claim」（mkstemp 完整寫入 + os.link——一個用 O_EXCL 建立的空 claim
  會讓一個 0 位元組的項目暴露出去，變成可被發布的狀態）；rename／
  os.replace **絕不能**當作 claim（同一個來源做兩次 rename 都會成功）。
  成功路徑上的 OSError 清理錯誤要被吞掉，這樣才不會把成功偽裝成失敗。
  〔檔案鎖 race／0 位元組發布 34⁄40／同時落地兩份 14⁄80／
  防毒軟體造成的一段 unlink 空窗期 → 永久卡住的重複項目〕
- **S2 · 跨行程鎖要有「偷鎖並重新仲裁」的機制。** 共享的 JSON 狀態 =
  在一個帶有 lockfile 的保護下進行讀取－合併－寫入，lockfile 內容帶有
  {pid,ts}；一個過期的持有者要用「PID 已死」的存活探測來偵測 → unlink
  後用 O_EXCL 重新建立；**絕不能**「逾時之後就直接無鎖繼續」。在 Windows
  上，`os.kill(pid, 0)` 會真的把行程殺掉——要用 OpenProcess 來探測。
  〔一個洩漏的 lockfile 悄悄讓互斥鎖失效；結果 32⁄40 同時落地兩份〕
- **S3 · 損毀的狀態要被隔離保存，絕不能直接重置。** 解碼失敗 → 複製一份到
  `.corrupt-<ts>` 並發出警報；一個靜默的 `state = {}` 會抹掉每個 agent
  的 last_run（上次執行紀錄）。
- **S4 · 每一個「最多執行一次」的標記，都要有對應的清除（CLEAR）動作。**
  項目狀態機的每一個終端邊都只能有一個清除呼叫點，並用一個生命週期測試
  來證明（發布 → gate →合法地重新進入 → 必須真的觸發 FRESH）；
  終端探測要檢查完整的叢集 key 集合，不能只抽樣代表性的一部分。
  〔殭屍草稿；被刪掉的項目又復活〕
- **S5 · 帳本的 key 在建立時就要凍結。** 結果／帳本紀錄要以 path.stem
  （在草稿建立當下就固定）為準來記錄，絕不能從可變動的內容重新計算
  （像是 slug(title)、hash(source_url)）——審查過程中人類的編輯會讓
  重新計算出來的 key 產生漂移。〔一次編輯悄悄改變了一筆紀錄的身分識別，
  並讓結果被重複記錄了兩次〕
- **S6 · 在第一個 await 之前就要先做重入防護。** 互動式的處理常式要在
  第一個同步區段就設好忙碌旗標，並在 `finally` 裡重置；長時間運行的
  互斥要用一個非阻塞的 `lock.locked()` 檢查。〔一次雙擊，在一個
  子行程執行期間讓檔案被同時搬動了兩次〕
- **S7 · 只附加（append-only）的追蹤紀錄，每次迭代第 0 步就要讀取。**
  迴圈絕不能跨次喚醒還信任自己的 context 記憶；一次迭代不能在沒有附加
  紀錄的情況下結束。（`loop-state.json` 就是這個追蹤紀錄——這正是為什麼
  一個全新的 orchestrator session 能夠在迴圈跑到一半時接手。）
- **S8 · 使用者的進行中工作（WIP）神聖不可侵犯。** 自主的 repo 操作 =
  連未追蹤檔案一起 stash + 從乾淨的基準分支出去 + 逐位元組驗證還原
  （之後的 porcelain 快照要完全一致）。

## P —— 行程、逾時、配額

- **P1 · 每一次 executor 派生，都要包一層 tree-kill（樹狀終止）。**
  對啟動器類 CLI 而言，`subprocess.run(timeout=)` 是假的（孫行程會佔住
  pipe → 造成掛起）；要用 Popen + 樹狀終止（`taskkill /T /F /PID`）。
  孤兒行程的清理只能透過一份持久化的自有 PID 登記表，並加上「映像檔名稱
  ＋PID 重用」防護——**絕不能**用 `/IM` 這種廣域終止。〔一次啟動時的
  `/IM` 終止，把人類自己正在使用的 session 也一併殺掉了〕
- **P2 · 逾時的先後順序要用算的，不能用猜的。** 外層逾時必須大於「內層
  最壞情況」（重試次數 × 每次呼叫逾時 + 退避總和）再加上啟動緩衝時間，
  並由一個從實際常數計算出來的防護測試釘住；逾時值要 ≥ 過去執行時間
  滾動平均值的 1.5 倍。〔一個 360 秒的外層逾時，在第 3 次嘗試時殺掉了
  一個實際耗時 545 秒的最壞情況內層呼叫〕
- **P3 · 每個項目都有各自的例外邊界；指標永遠要往前推進。** 單一項目
  當掉（或收到 429）不能拖垮整個迴圈；要記錄一筆有型別的錯誤紀錄，
  然後讓下一次迭代照常觸發。〔一次配額 429，讓一個排程器死了 40 小時〕
- **P4 · 先 claim 再 ack 的工作項目。** 在執行之前先把觸發檔重新命名成
  `.processing/<id>`；成功就刪除；失敗就送進死信佇列並發出警報；
  watchdog（看門狗）要斷言沒有任何 `.processing` 檔案的存在時間超過
  逾時上限。先刪除再執行 = 一旦崩潰就會靜默卡死。
- **P5 · 每一條退出路徑都要把已完成的工作攤出來。** 成功、逾時、例外、
  rc≠0 全部都要走同一個共用的攤出函式（每條路徑都要有測試）；
  面向使用者的錯誤文字要截斷到傳輸層的上限；摘要只回報這次執行實際
  量測到的計數器。〔一次跑了 20 分鐘的執行，在最後一步逾時，結果 8 筆
  真正完成的產出物完全不可見——人類看到的是「什麼都沒生出來」〕
- **P6 · 成本計算不能預設為 0。** 一個缺失的 cost 欄位要算成一次
  `cost_unknown`（成本未知）事件，連續 3 次就要發出警報；把 $0 當預設值
  會讓 budget gate 永久失明。〔呼叫端把 `cost_usd: 0.0` 寫死，結果一筆
  四位數的超支完全沒被看見〕
- **P7 · 釘住 context 的大小；出現連續完全相同的重複就要示警。** 派生
  要帶有 isolation（隔離）旗標；派生前要斷言 prompt 大小 <
  context 上限 − 安全邊界（有型別的 prompt_too_long）；同一個 agent
  連續 3 次完全相同的失敗 = 發出警報。〔一個繼承下來的 context 大小
  膨脹到 212K，導致每一輪都靜默失敗，連續好幾天都沒被發現〕

## F —— 新鮮度與空跑陷阱

- **F1 · 每一個外部輸入來源池，第 0 步都要有新鮮度斷言。**
  `max(published_date) >= now − freshness_budget`，不成立就擋住這個
  階段；任何雙模式（fixture／live）工具都必須把自己實際生效的模式回聲
  到 stdout，並由 gate 斷言它等於要求的模式。〔一個 fixture 模式的
  環境變數，讓某個資料來源變成靜默的空跑：一週前的舊資料通過了兩道
  綠燈 gate，直到人類問「為什麼都沒有最近的東西」才被發現〕
- **F2 · 行程存活（process-alive）不等於健康。** watchdog 要同時斷言
  輸出新鮮度（心跳檔 mtime 沒有超過最大存活時間）**以及**行程身分
  （PID 存活**且**命令列吻合）；偵測到過期的 pidfile 就刪除；每個
  元件只能有一個復原權責歸屬（{restart | alert_only}）——對一個本來就有
  原生重試機制的元件再自動重啟，會造成互相搶跑。
- **F3 · watchdog 的涵蓋範圍要被斷言，不能只是假設。** 一份機器可讀的
  「存活元件清單」，要跟每次執行實際檢查到的集合做差異比對；架構切換
  的 PR 必須在同一個 diff 裡更新這份清單。〔一次架構切換之後，新的
  pipeline 完全沒有任何新鮮度檢查——正是 watchdog 原本要防範的那種
  靜默停擺〕
- **F4 · 延後執行的 gate 要帶有存活性檢查。** 每一個 watch-gate 都要有
  `{precondition_check_cmd, hard_stop_date}`；當被參照的外部物件已經
  不可能再轉換狀態時，一次掃描要能標記出 UNREACHABLE（不可能再觸發）。
  〔一個綁定在某個 PR 上的 gate，那個 PR 自動關閉之後，這個 gate 就
  靜靜地死掉了〕

## E —— 編碼與環境

- **E1 · 每一個行程邊界都要釘住 UTF-8。** 每一個被派生出去的環境變數都要
  設 `PYTHONUTF8=1`；每一次讀取 subprocess 文字輸出都要用
  `encoding="utf-8", errors="replace"`（包括行程列表工具）；harness 的
  stdio 要重新設定；REST 的 request body 要預先編碼成 UTF-8 bytes；
  每個通道都要有一個 CJK＋emoji 的往返測試（同時也是對整類 bug 最直接
  的反證）。〔一個 judge 的 pipe、一個清理路徑的解碼當機，還有一個聊天
  通知程式，全都是同一種 bug，起因都是非 UTF-8 的預設編碼頁〕
- **E2 · Windows 上要用雙路徑宣告。** 任何同時會被 Python 與一個 POSIX
  shell 讀取的路徑，都要同時宣告 PATH_WIN（`C:/...`）與 PATH_UNIX
  （`/c/...`）兩種形式。〔一個驗證腳本只因為路徑寫法不同就誤判失敗〕

## A —— 自主性與上報

- **A1 · 收尾（closeout）要被授權、要有預算、而且要是終局性的。**
  預留一個明確的收尾時間窗；過了價值平緩點之後，只允許執行收尾用的
  迭代；停止（略過下一次喚醒）是一個由 spec 授權的正向動作。〔平緩點
  之後的迭代反而稀釋掉了一個原本乾淨的最終狀態〕
- **A2 · 負空間（negative space）是必要項目。** 最終的簡報要帶有一張
  `not_done`（未完成）表，每個「永遠不會自動完成」的類別各佔一列，
  附上實例數量與產出物路徑——這樣無人值守 agent 的責任歸屬才能被稽核，
  而不是只能靠「沒看到就當作沒發生」來推論。
- **A3 · 啟動門檻要依狀態判斷，不能只靠字句比對。** 觸發條件 =
  （有符合資格的待辦任務 AND 訊號類別），並在該回合結束前發出一個
  有型別的提議；精確字句比對會在失敗時直接關閉，等於什麼都沒偵測到。
  〔一個沒有講出那句「魔法字句」的啟動訊號，讓一個已經證實可用的
  harness 閒置著：11 個任務，0 個進展〕
