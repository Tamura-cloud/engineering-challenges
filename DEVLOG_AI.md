# Diário de Bordo & Decisões Técnicas (Takeovers Challenge)

Registro das decisões de arquitetura, ergonomia de desenvolvimento, estratégias de modelagem e validação da divisão de responsabilidades entre Humano e IA.

---

## 📅 Sessão 1: 14/09/2026 — Fundação, Ergonomia & Validação de Grounding

### 1. Escopo e Restrições de Projeto
* **Objetivo:** Reconstrução histórica de 20 anos da estrutura societária e capital social da **ARCHEAN TECHNOLOGIES (SIREN 480489707)** a partir de 17 atos jurídicos e saídas de OCR a 300 DPI.
* **Planejamento Temporal:** Cronograma modular de **4 etapas de ~2 horas** (totalizando ~8 horas, respeitando rigorosamente o limite de escopo sugerido pelos avaliadores no briefing).

### 2. Ergonomia de Desenvolvimento & Tooling Interno
* **Identificação de Atrito Operacional:** O script oficial de conferência (`tools/bbox_viewer.py`) exigia parametrização manual de caminhos extensos de diretórios para cada inspeção.
* **Solução Arquitetural:** Desenvolveu-se o wrapper utilitário `quick_check.py`, que:
  * Indexa e mapeia automaticamente os 17 documentos e respectivos diretórios de OCR;
  * Extrai do metadata do INPI os assuntos/decisões declaradas de cada ato, permitindo filtragem prévia dos documentos com impacto efetivo em capital;
  * Permite busca textual (`--grep`) e renderização imediata com abertura automática do artefato de inspeção (`visualizacao.png`).

### 3. Análise de Resolução & Grounding (300 DPI vs. 150 DPI vs. Normalização 0–1)
* **Avaliação Crítica do Pipeline:**
  * O OCR bruto fornecido foi processado a **300 DPI** com coordenadas absolutas em pixels (`polygon`).
  * A entrega exigida pelo schema (`results.schema.json`) requer coordenadas **normalizadas de 0.0 a 1.0**, garantindo total independência de resolução.
  * O utilitário de visualização renderiza a **150 DPI** para otimização de I/O e performance, aplicando a multiplicação proporcional das coordenadas normalizadas sobre a matriz de renderização.
* **Validação Empírica:** Auditoria visual do Documento 1 (Constituição de 2005), Página 1, confirmando a extração e enquadramento exato da menção do capital inicial de **37.000 €** no bounding box normalizado `[0.3895, 0.0615, 0.6167, 0.0758]`.

---

## 📅 Sessão 2: 15/09/2026 — Reconciliação Algébrica, Invariantes Societários & Construção da Linha do Tempo

### 1. Modelagem Contábil e Invariantes Algébricos ($n-1 \leftrightarrow n \leftrightarrow n+1$)
* **Decisão Arquitetural (Trade-off de Engenharia):** Em vez de implementar uma infraestrutura prematura e genérica de grafos multidimensionais (risco de *overengineering* e estouro do orçamento de tempo), o problema foi formalizado como uma **Máquina de Estados Finitos (FSM) com Conservação de Fluxo**:
  $$\text{Capital (€)} = \text{Total de Cotas/Ações} \times \text{Valor Nominal (€)}$$
  $$\sum_{i \in \text{Sócios}} \text{Cotas}_i = \text{Total de Cotas} \quad \text{e} \quad \sum \%_i = 100\%$$
  $$\text{Estado } S_n = S_{n-1} + \Delta\text{Ações}_{evento}$$
* **Isolamento e Rastreamento de Conflitos Documentais:**
  * **Ato 3 (2005):** A ata constata expressamente que o protocolo de cessão anterior *"contient une erreur"* retificada pelos registros de títulos.
  * **Ato 4 (2006):** Na folha de presença da AGE de 20/10/2006, identifica-se o rebalanceamento de 20 ações entre Xavier Aumont (637 ações) e Antonio Blanco (803 ações), antes do aumento de capital de 50.000 € e da cessão de 225 ações para Michel Capgras.
  * **Ato 15 (2018):** Identificou-se um erro tipográfico material no texto da alteração do Artigo 6 (que cita erroneamente "185 759 euros"), ao passo que a 1ª Deliberação e o fechamento contábil aprovam expressamente "182 759 euros" para atingir o capital cravado de 400.000 €.

### 2. Descoberta Chave do Grupo Societário (Bônus Integrado)
* No **Documento 6 (2008-06-27)** e **Documento 14 (2017-03-28)**, identificou-se a entrada e controle integral da **HADEAN (SIREN 499979540)** como *Associée Unique* da Archean Technologies.
* Isso permitiu conectar o desafio principal ao bônus do grupo (`group.nodes` e `group.edges`) com proveniência comprovada em ata e coordenadas normalizadas.

### 3. Pipeline de Reconciliação e Validação de Schema
* Implementação do motor `reconcile_timeline.py`, responsável por:
  * Extrair 22 eventos com grounding estrito (`inpi_id`, `page`, `bbox` normalizado `0-1`, `snippet`);
  * Construir a `capital_timeline` cronológica em 6 estados consolidados;
  * Testar e aprovar 100% dos 3 invariantes algébricos;
  * Validar a saída final contra o JSON Schema oficial (`challenges/actes/schema/results.schema.json`) e gerar o `results.json` na raiz do projeto.

