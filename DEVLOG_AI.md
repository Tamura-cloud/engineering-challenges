# Diário de Bordo — Decisões e Achados

Registra **o que mudou de rumo**, não a cronologia do trabalho. Onde um achado contradisse
uma decisão anterior, fica registrado o achado — inclusive quando o erro foi nosso.

---

## Escopo e decisão de modelagem

Reconstruir 20 anos de composição de capital da **ARCHEAN TECHNOLOGIES (SIREN 480489707)**
a partir de 17 atos e do OCR a 300 dpi. Duas entregas num só `results.json`: `events[]` (os
movimentos, com proveniência) e `capital_timeline[]` (o estado após cada um).

O problema foi formalizado como **máquina de estados com conservação de fluxo**, e não como
grafo genérico — decisão tomada para não pagar abstração antes de ter dado:

$$\text{capital} = \text{cotas} \times \text{nominal} \qquad \sum_i \text{cotas}_i = \text{total} \qquad \sum_i \%_i = 100\%$$

O grafo societário veio depois e só para o bônus, e como **dado**, não como motor.

---

## Os sete achados que importam

**1. O OCR não é fonte de verdade — a imagem é.** Um audit inicial comparava o JSON contra o
texto do OCR, então qualquer trecho que discordasse de uma linha corrompida parecia
inventado. A imagem mostra `(37.000)` onde o OCR diz `(37.0o0)`. A ordem de verificação foi
invertida: imagem primeiro, OCR só como localizador.

**2. Confiança do OCR não detecta erro.** A linha comprovadamente errada `(37.0o0)` pontua
**0.988**, contra mediana de 0.991 do corpus. Filtrar por `score` não acha nada; a detecção
teve de migrar para padrões de token numérico (`src/ocr_audit.py`).

**3. Duas fontes legíveis que discordam, e nenhum invariante que as distinga.** O ato de
2006-01-04 dá a repartição pós-trespasse como **823/617** para Blanco/Aumont; a folha de
presença certificada de 20/10/2006 traz **803/637**, conferidos na imagem renderizada, com a
menção *"Certifiée sincère et véritable"*. As duas somam 1.500 com Gicquel, então o
fechamento não decide — e **não é erro de OCR**. A **lista de subscrição desempata**: o ato
de 2007-02-20 reserva as 500 ações novas em `Pour 330 actions` para Aumont, `Pour 150` para
Blanco e `Pour 20` para Gicquel, e só a base 803/637 fecha com o estado seguinte (com 823,
Blanco terminaria em 973, não 953). Se as duas fontes estiverem certas, houve um movimento de
20 ações entre as duas datas que nenhum ato documenta. Fica **declarado, não resolvido**.

**4. O mesmo erro de novo, do outro lado.** Em 2022 o modelo leu 7.140/6.860 cotas *novas* e
o ledger **atribuiu** em vez de **somar** — 14.000 cotas sobre um capital de 150.000 € a 10 €
nominal, **15× de erro** no denominador da cap table. A numeração das próprias cotas no ato
("de 1 à 510 et de 1001 à 8140") prova que o modelo estava certo e o ledger errado.

**5. Datas de efeito não são datas de depósito.** O brief avisa; ainda assim erramos duas
vezes, por escrito. Os aportes à HADEAN têm efeito em **07/09/2007** e **18/04/2008**, e foram
depositados em 18/09/2007 e 30/04/2008.

**6. A prova de grupo mora na pasta da controladora.** As saídas de Aumont (742), Gicquel (80)
e Capgras (225) não estão em nenhum ato da Archean — estão nos da HADEAN. O benchmark e o
validador de datas só olhavam a pasta do sujeito, e por isso reportavam `AUSENTE` para
citações que existiam, ou acusavam "depósito ausente" em sete eventos. Ambos passaram a
procurar no acervo inteiro.

**7. O que não fecha, não se esconde.** Restou uma lacuna: as **953 ações de Antonio BLANCO
MARINA**. Nenhum ato dos dois acervos registra a saída dele; uma varredura completa do OCR
encontra o nome 11 vezes, todas nos documentos da própria Archean. É a única falha de
invariante do entregável — declarada, com o método da varredura junto, para que se saiba que
a lacuna é delimitada e não suposta.

---

## Uma lição de método, que custou caro

O `README.md` afirmava que o `results.json` era "produced by a deterministic ledger". Não era:
os estados são digitados à mão e conferidos por invariantes. A auditoria passou a cobrar a
definição do próprio brief — `capital_timeline[]` é *"the state of the cap table after each of
those events"* — e foi assim que apareceu um estado datado de `2005-05-17` cujas causas
declaradas eram todas de `2005-08-16`.

O entregável não ficou pior por causa disso. Ficou mais honesto: **81/82 invariantes**, com a
única falha nomeada, em vez de um número bonito e uma descrição falsa.

---

## Papéis: o que a IA fez e o que foi conferido

**A IA** redigiu a geometria com PyMuPDF, o casador tolerante a erros de OCR
(`src/grounding.py`), o ledger, os invariantes e os renderizadores dos relatórios. Também
varreu os atos para localizar movimentos e datas.

**Foi conferido à mão**, contra a imagem renderizada da página — e não contra o texto do OCR:
cada contagem de cotas e cada data da timeline.

**Onde a IA errou** está na §4 do `README.md`, em seis itens. Quatro deles foram encontrados
pelas próprias verificações, que é exatamente para isso que elas existem.


### 2. Descoberta Chave do Grupo Societário (Bônus Integrado)
* No **Documento 6 (2008-06-27)** e **Documento 14 (2017-03-28)**, identificou-se a entrada e controle integral da **HADEAN (SIREN 499979540)** como *Associée Unique* da Archean Technologies.
* Isso permitiu conectar o desafio principal ao bônus do grupo (`group.nodes` e `group.edges`) com proveniência comprovada em ata e coordenadas normalizadas.

### 3. Pipeline de Reconciliação e Validação de Schema
* Implementação do motor `reconcile_timeline.py`, responsável por:
  * Extrair 22 eventos com grounding estrito (`inpi_id`, `page`, `bbox` normalizado `0-1`, `snippet`);
  * Construir a `capital_timeline` cronológica em 6 estados consolidados;
  * Testar e aprovar 100% dos 3 invariantes algébricos;
  * Validar a saída final contra o JSON Schema oficial (`challenges/actes/schema/results.schema.json`) e gerar o `results.json` na raiz do projeto.

