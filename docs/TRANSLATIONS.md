# Traduções

35 idiomas em `src/nova_dm/translations/` (`.ts` fonte, `.qm` compilado): as 24 línguas oficiais da UE
(bg, hr, cs, da, nl, en, et, fi, fr, de, el, hu, ga, it, lv, lt, mt, pl, pt_PT, ro, sk, sl, es, sv) mais ca, gl, eu, nb, is, sq, sr, mk, bs, uk, ru, cy.

**Aviso:** as traduções foram geradas por IA e **não foram revistas por falantes nativos**. Confiança menor em: ga, mt, is, sq, sr, mk, bs, gl, eu, cy.
Correções são bem-vindas: editar o `.ts` e correr `python scripts/compile_translations.py`.

- Novo idioma: `python scripts/update_translations.py --new <código>`, traduzir, compilar.
- Depois de mudar textos no código: `python scripts/update_translations.py`.
- `tests/test_translations.py` valida completude, marcadores `{x}` e quebras de linha.
