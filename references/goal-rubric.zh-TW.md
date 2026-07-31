> 此為 `goal-rubric.md` 的中文對照版，僅供閱讀參考；skill 實際載入與生效的是英文版原始檔案。

# Goal Rubric（目標評分準則，Stage 1）

把使用者的 goal（目標）逼到讓兩個能力相當的 agent 對「完成了沒有」不會有分歧為止。

## 一個好的 goal 會指名
- 具體的**產出物（OUTCOME artifact）**，而不是活動本身（例如「一份排序好的
  5 項候選清單」，而不是「幫我挑主題」）。
- 能**證明**迴圈已經完成的狀態（definition_of_done，完成定義）。
- 範圍邊界：包含什麼、排除什麼、最大深度。
- builder 必須**讀取**而不能靠假設的 context sources（情境來源）。
- 誰會使用這個結果（使用者本人／某個讀者／下游的另一個 agent）。

## 嚴格模式下的批評提問（每一條都要問）
- 「如果兩個 agent 意見不合，要靠哪個產出物來裁決？」
- 「這裡有哪些字眼是主觀的，需要一個可量測的替代指標？」
- 「builder 在草擬計畫之前必須先讀什麼？」
- 「有什麼是明確排除在範圍之外的？」
- 「這件事能不能拆成 plan／delivery／verification 三種產出物？」

## Anti-patterns（反面模式，要擋下來，不要接受）
- 「改善／弄好一點／做得更好」卻沒有指定目標產出物。
- 「研究 X」卻沒有這份研究要支撐的任何決策。
- 成功與否取決於這個迴圈根本不會去蒐集的資訊。
- 沒完沒了的打磨，卻沒有一個停止狀態。

## Before -> after（修改前 -> 修改後）
較弱：「把 onboarding 文件整理一下。」
較好：「產出 `docs/quickstart.md`，讓一個新貢獻者能從全新 clone 一路走到測試
         通過：Prerequisites／Install／Run tests／Troubleshooting，每一步都是
         可以直接複製貼上執行的指令，不能有任何 TODO。」

較弱：「把 API 弄快一點。」
較好：「把 `GET /search` 的 p95 延遲，用 `bench/search.py` 對照 fixture corpus
         （固定測試資料集）量測，壓到 200ms 以下，而且不能有任何 endpoint 回傳
         跟現在不一樣的結果。」
