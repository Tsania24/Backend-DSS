# Daftar Item untuk Perbaikan Manual

**Dibuat:** 2026-11-20 18:08  
**File target:** `data/markdown/furniture_arrangement_ieq_2023_rebuilt.md`  
**Total item:** 0 (0 HIGH, 0 MEDIUM, 0 LOW)

> **Catatan:** Item ini tidak bisa diperbaiki otomatis. Item HIGH harus diselesaikan
> sebelum pipeline RAG dapat dijalankan dengan benar.

---

---

## Panduan Perbaikan Rumus LaTeX

Semua rumus berikut tersedia di versi LlamaParse playground:
`data/llamaparse_playground_original/furniture_arrangement_ieq_2023.md`

Format yang benar adalah `$$...$$` untuk display math dan `$...$` untuk inline math.

### Rumus Utama (dari paper)

| No. | Deskripsi | LaTeX |
|-----|-----------|-------|
| 1 | Bellman Equation | `$$Q(s, a) \leftarrow (1-\alpha)Q(s,a) + \alpha[R + \gamma \cdot \max_{a'} Q(s',a')]$$` |
| 2 | Q̂-vector | `$$\hat{Q}(s, a) = (\hat{Q}_1(s, a), \dots, \hat{Q}_m(s, a))$$` |
| 3 | SQ scalarized | `$$SQ(s, a) = \sum_{i=1}^{m} w_i Q_i(s, a)$$` |
| 7 | Sound pressure | `$$L_{Receiver} = L_{Source} + 10\log(Q/(4\pi r^2) + 4/Ac_R)$$` |
| 16 | R_IEQ | `$$R_{IEQ} = p_{TC} \cdot TC_{index} + p_{AC} \cdot AC_{index} + p_{VC} \cdot VC_{index}$$` |
