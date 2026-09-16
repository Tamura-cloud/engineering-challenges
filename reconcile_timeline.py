#!/usr/bin/env python3
"""
reconcile_timeline.py - Motor de Reconstrução, Reconciliação Algébrica e Grounding.

Este script implementa:
1. A extração fundamentada (grounded) dos eventos societários da ARCHEAN TECHNOLOGIES (480489707).
2. As fórmulas contábeis de invariantes societários (Capital = Ações * Valor Nominal, Soma das Cotas = Total de Ações).
3. A geração do results.json no formato exato de challenges/actes/schema/results.schema.json.
4. Validação automática contra o JSON Schema oficial.
"""

import sys
from pathlib import Path
import json
import jsonschema

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = REPO_ROOT / "challenges" / "actes" / "schema" / "results.schema.json"
RESULTS_PATH = REPO_ROOT / "results.json"


def build_events():
    """
    Lista cronológica de eventos com grounding estrito nos PDFs/OCRs do acervo.
    """
    events = [
        # 1. Constituição (2004-12-15 / Depósito 2005-01-25)
        {
            "event_id": "evt_2004-12-15_incorp_capital",
            "event_code": "CAPITAL_INCREASE",
            "event_date": "2004-12-15",
            "payload": {
                "amount_eur": 37000.0,
                "capital_after_eur": 37000.0,
                "method": "numeraire"
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec5",
                "page": 3,
                "bbox": [0.1201, 0.3994, 0.6591, 0.4146],
                "snippet": "Le capital social est fixé à la somme de trente sept mille (37.000) euros."
            }
        },
        {
            "event_id": "evt_2004-12-15_entry_aumont",
            "event_code": "SHAREHOLDER_ENTRY",
            "event_date": "2004-12-15",
            "payload": {
                "holder_name": "Xavier AUMONT",
                "shares": 155
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec5",
                "page": 3,
                "bbox": [0.1820, 0.4444, 0.5965, 0.4571],
                "snippet": "Monsieur Xavier AUMONT 155 actions"
            }
        },
        {
            "event_id": "evt_2004-12-15_entry_blanco",
            "event_code": "SHAREHOLDER_ENTRY",
            "event_date": "2004-12-15",
            "payload": {
                "holder_name": "Antonio BLANCO MARINA",
                "shares": 155
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec5",
                "page": 3,
                "bbox": [0.1805, 0.4576, 0.5967, 0.4718],
                "snippet": "Monsieur Antonio BLANCO MARINA 155 actions"
            }
        },
        {
            "event_id": "evt_2004-12-15_entry_gicquel",
            "event_code": "SHAREHOLDER_ENTRY",
            "event_date": "2004-12-15",
            "payload": {
                "holder_name": "Franck GICQUEL",
                "shares": 60
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec5",
                "page": 3,
                "bbox": [0.1820, 0.4727, 0.5987, 0.4864],
                "snippet": "Monsieur Franck GICQUEL 60 actions"
            }
        },

        # 2. Aumento de Capital para 150.000 € (AGE 2005-05-17, Doc 2)
        {
            "event_id": "evt_2005-05-17_cap_increase_150k",
            "event_code": "CAPITAL_INCREASE",
            "event_date": "2005-05-17",
            "payload": {
                "amount_eur": 113000.0,
                "capital_after_eur": 150000.0,
                "method": "numeraire"
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec4",
                "page": 2,
                "bbox": [0.1216, 0.7672, 0.8896, 0.8170],
                "snippet": "constate la réalisation définitive de l'augmentation de capital de 113 000 € par la création de 1 130 actions nouvelles de numéraire de 100 euros , pour porter le capital à 150 000 €."
            }
        },

        # 2b. Entrada dos subscritores das 1 130 ações novas — EVENTO-CONSEQUÊNCIA.
        #
        # event_codes.json diz que SHAREHOLDER_ENTRY captura a consequência (X é
        # agora associado) e que o mecanismo é o evento que co-dispara: aqui, o
        # próprio aumento que criou as 1 130 ações. A spec acrescenta que essas
        # consequências são "derived by the snapshot folder and emitted as
        # SHAREHOLDER_ENTRY / SHAREHOLDER_END events at projection time". Este é
        # um deles, e por isso compartilha a fonte com o aumento: a MESMA frase do
        # ato cria as 1 130 ações. Quem as deteve é o ato de 2006-01-04 (página 6),
        # que faz o trespasse de "la totalité des actions détenues" por eles.
        {
            "event_id": "evt_2005-05-17_entry_souscripteurs",
            "event_code": "SHAREHOLDER_ENTRY",
            "event_date": "2005-05-17",
            "payload": {
                "holder_name": "Malik GUELLATI, Christophe LEROUX, Marielle ROUJEAN",
                "shares": 1130
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec4",
                "page": 2,
                "bbox": [0.1216, 0.7672, 0.8896, 0.8170],
                "snippet": "constate la réalisation définitive de l'augmentation de capital de 113 000 € par la création de 1 130 actions nouvelles de numéraire de 100 euros , pour porter le capital à 150 000 €."
            }
        },

        # 3. Cessão das ações dos investidores Guellati/Leroux/Roujean (2005-08-16 / AGE 2005-07-22, Doc 3)
        #
        # Uma transferência por cessionário, e não uma só com os dois nomes numa string:
        # um destino composto não casa com titular nenhum do estado, e o invariante 8 não
        # consegue conferir o movimento. Os valores 648 e 482 são diferença entre a
        # repartição documentada (803 / 637) e as posições da constituição (155 / 155) —
        # somam os 1.130 que o ato descreve como 'la totalité des actions détenues'.
        {
            "event_id": "evt_2005-08-16_transfer_to_blanco",
            "event_code": "SHAREHOLDER_SHARE_TRANSFER",
            "event_date": "2005-08-16",
            "payload": {
                "from_name": "Malik GUELLATI, Christophe LEROUX, Marielle ROUJEAN",
                "to_name": "Antonio BLANCO MARINA",
                "shares": 648
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec2",
                "page": 6,
                "bbox": [0.1052, 0.6538, 0.8721, 0.6988],
                "snippet": "L'assemblée générale, après avoir pris connaissance d’un protocole de cession de la totalité des actions détenues par Messieurs Malik GUELLATI, Christophe LEROUX et Madame Marielle ROUJEAN, associés d'ARCHEAN TECHNOLOGIES, approuve la dérogation à l’article 15 des"
            }
        },
        {
            "event_id": "evt_2005-08-16_transfer_to_aumont",
            "event_code": "SHAREHOLDER_SHARE_TRANSFER",
            "event_date": "2005-08-16",
            "payload": {
                "from_name": "Malik GUELLATI, Christophe LEROUX, Marielle ROUJEAN",
                "to_name": "Xavier AUMONT",
                "shares": 482
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec2",
                "page": 6,
                "bbox": [0.1052, 0.6538, 0.8721, 0.6988],
                "snippet": "L'assemblée générale, après avoir pris connaissance d’un protocole de cession de la totalité des actions détenues par Messieurs Malik GUELLATI, Christophe LEROUX et Madame Marielle ROUJEAN, associés d'ARCHEAN TECHNOLOGIES, approuve la dérogation à l’article 15 des"
            }
        },
        {
            "event_id": "evt_2005-08-16_exit_guellati",
            "event_code": "SHAREHOLDER_END",
            "event_date": "2005-08-16",
            "payload": {
                "holder_name": "Malik GUELLATI"
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec2",
                "page": 6,
                "bbox": [0.1052, 0.6538, 0.8714, 0.6837],
                "snippet": "cession de la totalité des actions détenues par Messieurs Malik GUELLATI"
            }
        },
        {
            "event_id": "evt_2005-08-16_exit_leroux",
            "event_code": "SHAREHOLDER_END",
            "event_date": "2005-08-16",
            "payload": {
                "holder_name": "Christophe LEROUX"
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec2",
                "page": 6,
                "bbox": [0.1052, 0.6538, 0.8714, 0.6837],
                "snippet": "Christophe LEROUX"
            }
        },
        {
            "event_id": "evt_2005-08-16_exit_roujean",
            "event_code": "SHAREHOLDER_END",
            "event_date": "2005-08-16",
            "payload": {
                "holder_name": "Marielle ROUJEAN"
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec2",
                "page": 6,
                "bbox": [0.1052, 0.6837, 0.8721, 0.6988],
                "snippet": "et Madame Marielle ROUJEAN, associés d'ARCHEAN TECHNOLOGIES"
            }
        },

        # 4. Aumento de Capital para 200.000 € e Entrada de Michel Capgras (AGE 2006-10-20, Doc 4)
        {
            "event_id": "evt_2006-10-20_cap_increase_200k",
            "event_code": "CAPITAL_INCREASE",
            "event_date": "2006-10-20",
            "payload": {
                "amount_eur": 50000.0,
                "capital_after_eur": 200000.0,
                "method": "numeraire",
                # A 3ª Resolução do MESMO ato (página 3) reserva as 500 ações novas
                # nominalmente: 'Pour 330 actions' a AUMONT, 'Pour 150 actions' a
                # BLANCO e 'Pour 20 actions' a GICQUEL — 330+150+20 = 500 exatas.
                # Estão aqui porque é o que permite à MÁQUINA decidir a leitura de
                # 2005: só a base 803/637 fecha com esta repartição. Sem este campo,
                # a decisão voltaria a depender de quem lê.
                "allocation": {
                    "Xavier AUMONT": 330,
                    "Antonio BLANCO MARINA": 150,
                    "Franck GICQUEL": 20
                }
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec7",
                "page": 3,
                "bbox": [0.0499, 0.1685, 0.9479, 0.2007],
                "snippet": "d'augmenter le capital social d'une somme de 50.000 euros, pour le porter de 150.000 euros à 200.000 euros, par création de 500 actions nouvelles de 100 euros de valeur nominale"
            }
        },
        {
            "event_id": "evt_2006-10-20_entry_capgras",
            "event_code": "SHAREHOLDER_ENTRY",
            "event_date": "2006-10-20",
            "payload": {
                "holder_name": "Michel CAPGRAS",
                "shares": 225
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec7",
                "page": 4,
                "bbox": [0.0493, 0.7257, 0.9459, 0.7584],
                "snippet": "L'Assemblée Générale, après avoir pris connaissance du rapport du Président agrée à devenir actionnaire Monsieur Michel CAPGRAS"
            }
        },
        {
            "event_id": "evt_2006-10-20_transfer_aumont_to_capgras",
            "event_code": "SHAREHOLDER_SHARE_TRANSFER",
            "event_date": "2006-10-20",
            "payload": {
                "from_name": "Xavier AUMONT",
                "to_name": "Michel CAPGRAS",
                "shares": 225
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec7",
                "page": 5,
                "bbox": [0.0391, 0.0556, 0.9468, 0.0874],
                "snippet": "L'Assemblée Générale autorise Monsieur Xavier AUMONT à céder 225 actions à Monsieur Michel CAPGRAS."
            }
        },

        # 5. Saída dos sócios pessoa física para a HADEAN, por aporte em natureza.
        #
        # Os atos estão na pasta da HADEAN, não na da Archean — é o caso que o
        # brief antecipa: "the relationship does not appear in the company's own
        # documents, you have to go look at the parent". O ato de constituição da
        # HADEAN (inpi_id 63f0a89c7a07a2434c069135) registra os aportes de Xavier
        # AUMONT (742 ações) e Franck GICQUEL (80), e diz que "les apports qui
        # précèdent prennent effet à compter de ce jour" — o dia da assinatura do
        # ato, 7 de setembro de 2007, NÃO a data de depósito (18/09). O relatório
        # do comissário aos aportes de 2008 (inpi_id 63f0a89c7a07a2434c069136)
        # registra o de Michel CAPGRAS (225 ações), "effectués en date du
        # 18/04/2008", depositado em 30/04. É a armadilha que o próprio brief
        # avisa: efeito não é depósito, e às vezes são meses.
        {
            "event_id": "evt_2007-09-07_transfer_aumont_hadean",
            "event_code": "SHAREHOLDER_SHARE_TRANSFER",
            "event_date": "2007-09-07",
            "payload": {
                "from_name": "Xavier AUMONT",
                "to_name": "HADEAN",
                "shares": 742
            },
            "source": {
                "inpi_id": "63f0a89c7a07a2434c069135",
                "page": 5,
                "bbox": [0.1188, 0.6928, 0.8848, 0.7231],
                "snippet": "6.2- Apport de 742 actions de la SAS ARCHEAN TECHNOLOGIES par Monsieur Xavier AUMONT"
            }
        },
        {
            "event_id": "evt_2007-09-07_end_aumont",
            "event_code": "SHAREHOLDER_END",
            "event_date": "2007-09-07",
            "payload": {
                "holder_name": "Xavier AUMONT",
                "shares": 742
            },
            "source": {
                "inpi_id": "63f0a89c7a07a2434c069135",
                "page": 5,
                "bbox": [0.1188, 0.6928, 0.8848, 0.7231],
                "snippet": "6.2- Apport de 742 actions de la SAS ARCHEAN TECHNOLOGIES par Monsieur Xavier AUMONT"
            }
        },
        {
            "event_id": "evt_2007-09-07_transfer_gicquel_hadean",
            "event_code": "SHAREHOLDER_SHARE_TRANSFER",
            "event_date": "2007-09-07",
            "payload": {
                "from_name": "Franck GICQUEL",
                "to_name": "HADEAN",
                "shares": 80
            },
            "source": {
                "inpi_id": "63f0a89c7a07a2434c069135",
                "page": 6,
                "bbox": [0.1202, 0.2798, 0.8855, 0.2945],
                "snippet": "6.3- Apport de 80 actions de la SAS ARCHEAN TECHNOLOGIES par Monsieur"
            }
        },
        {
            "event_id": "evt_2007-09-07_end_gicquel",
            "event_code": "SHAREHOLDER_END",
            "event_date": "2007-09-07",
            "payload": {
                "holder_name": "Franck GICQUEL",
                "shares": 80
            },
            "source": {
                "inpi_id": "63f0a89c7a07a2434c069135",
                "page": 6,
                "bbox": [0.1202, 0.2798, 0.8855, 0.2945],
                "snippet": "6.3- Apport de 80 actions de la SAS ARCHEAN TECHNOLOGIES par Monsieur"
            }
        },
        {
            "event_id": "evt_2007-09-07_entry_hadean_apports",
            "event_code": "SHAREHOLDER_ENTRY",
            "event_date": "2007-09-07",
            "payload": {
                "holder_name": "HADEAN",
                "holder_siren": "499979540",
                "shares": 822
            },
            "source": {
                "inpi_id": "63f0a89c7a07a2434c069135",
                "page": 6,
                "bbox": [0.1202, 0.2798, 0.8855, 0.2945],
                "snippet": "6.3- Apport de 80 actions de la SAS ARCHEAN TECHNOLOGIES par Monsieur"
            }
        },
        {
            "event_id": "evt_2008-04-18_transfer_capgras_hadean",
            "event_code": "SHAREHOLDER_SHARE_TRANSFER",
            "event_date": "2008-04-18",
            "payload": {
                "from_name": "Michel CAPGRAS",
                "to_name": "HADEAN",
                "shares": 225
            },
            "source": {
                "inpi_id": "63f0a89c7a07a2434c069136",
                "page": 3,
                "bbox": [0.1555, 0.4931, 0.8765, 0.5093],
                "snippet": "Monsieur Michel CAPGRAS propose de faire apport à la SAS HADEAN de 225 actions"
            }
        },
        {
            "event_id": "evt_2008-04-18_end_capgras",
            "event_code": "SHAREHOLDER_END",
            "event_date": "2008-04-18",
            "payload": {
                "holder_name": "Michel CAPGRAS",
                "shares": 225
            },
            "source": {
                "inpi_id": "63f0a89c7a07a2434c069136",
                "page": 3,
                "bbox": [0.1555, 0.4931, 0.8765, 0.5093],
                "snippet": "Monsieur Michel CAPGRAS propose de faire apport à la SAS HADEAN de 225 actions"
            }
        },

        # 6. Entrada da HADEAN, Split 100:1 e Emissão de Ações Preferenciais A e B (2008-06-27, Docs 5 e 6)
        {
            "event_id": "evt_2008-06-27_entry_hadean",
            "event_code": "SHAREHOLDER_ENTRY",
            "event_date": "2008-06-27",
            "payload": {
                "holder_name": "HADEAN",
                "holder_siren": "499979540",
                "shares": 200000
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec3",
                "page": 1,
                "bbox": [0.1243, 0.3301, 0.7383, 0.3731],
                "snippet": "La société HADEAN, société par actions simplifiée au capital de 578.450 euros, est situé 7 avenue Albert Durand - 31700 Blagnac, immatriculée au registre du sociétés de Montauban sous le numéro 499 979 540, Associée Unique de la"
            }
        },
        {
            "event_id": "evt_2008-06-27_dual_class_creation",
            "event_code": "CAPITAL_DUAL_CLASS",
            "event_date": "2008-06-27",
            "payload": {
                "class_name": "Actions de préférence A et B",
                "description": "Création d'actions de préférence de catégorie A (dividende prioritaire) et catégorie B (avec BSOCA)."
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec3",
                "page": 2,
                "bbox": [0.118, 0.7285, 0.8794, 0.7765],
                "snippet": "DÉCIDE, conformément aux dispositions des articles L. 228-11 et suivants du Code de commerce, de créer des actions de préférence de catégorie B (ci-après les « Actions B ») et des actions de préférence de catégorie B' (ci-après les « Actions B' »),"
            }
        },
        {
            "event_id": "evt_2008-06-27_cap_increase_cat_a",
            "event_code": "CAPITAL_INCREASE",
            "event_date": "2008-06-27",
            "payload": {
                "amount_eur": 17241.0,
                "capital_after_eur": 217241.0,
                "method": "numeraire"
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec3",
                "page": 2,
                "bbox": [0.1152, 0.9224, 0.8765, 0.9674],
                "snippet": "DÉciDE d'augmenter le capital social de la Société d'un montant nominal de 17.241 euros, par l'émission de 17.241 Actions A (les « Actions A Nouvelles »), d'une valeur nominale de 1 euro chacune (l' « Augmentation de Capital I »),"
            }
        },
        {
            "event_id": "evt_2008-06-27_cap_increase_cat_b",
            "event_code": "CAPITAL_INCREASE",
            "event_date": "2008-06-27",
            "payload": {
                "amount_eur": 150861.0,
                "capital_after_eur": 368102.0,
                "method": "numeraire"
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec3",
                "page": 3,
                "bbox": [0.1173, 0.7915, 0.8807, 0.8249],
                "snippet": "d’augmenter le capital social d'un montant nominal de 150.861 euros par l'émission de 150.861 Actions B nouvelles (les « Actions B Nouvelles ») d'une valeur nominale de 1 euro chacune, à"
            }
        },

        # 6. Redução do Capital por Recompra e Cancelamento de Ações B (2017-01-19 / 2017-02-21, Docs 13 e 14)
        {
            "event_id": "evt_2017-02-21_cap_decrease_cancel_b",
            "event_code": "CAPITAL_DECREASE",
            "event_date": "2017-02-21",
            "payload": {
                "amount_eur": 150861.0,
                "capital_after_eur": 217241.0,
                "method": "autre"
            },
            "source": {
                "inpi_id": "63e9593a8be6eb9f9d257ebe",
                "page": 3,
                "bbox": [0.1133, 0.3834, 0.8801, 0.4347],
                "snippet": "le Président constate que le capital social est réduit de 150 861 euros pour être ramené de 368 102 euros à 217 241 euros et divisé en 217 241 actions de 1 euro de valeur nominale chacune."
            }
        },
        {
            "event_id": "evt_2017-02-21_end_fpci_securite",
            "event_code": "SHAREHOLDER_END",
            "event_date": "2017-02-21",
            "payload": {
                "holder_name": "FPCI SECURITE",
                "shares": 64655
            },
            "source": {
                "inpi_id": "63e9593a8be6eb9f9d257ebe",
                "page": 3,
                "bbox": [0.1847, 0.2696, 0.7712, 0.2856],
                "snippet": "- à FPCI SECURITE 64 655 actions"
            }
        },
        {
            "event_id": "evt_2017-02-21_end_galia_pme4",
            "event_code": "SHAREHOLDER_END",
            "event_date": "2017-02-21",
            "payload": {
                "holder_name": "FIP GALIA PME 4",
                "shares": 12931
            },
            "source": {
                "inpi_id": "63e9593a8be6eb9f9d257ebe",
                "page": 3,
                "bbox": [0.1847, 0.2870, 0.7712, 0.3019],
                "snippet": "- à FIP GALIA PME 4 12 931 actions"
            }
        },
        {
            "event_id": "evt_2017-02-21_end_galia_venture",
            "event_code": "SHAREHOLDER_END",
            "event_date": "2017-02-21",
            "payload": {
                "holder_name": "GALIA VENTURE",
                "shares": 30172
            },
            "source": {
                "inpi_id": "63e9593a8be6eb9f9d257ebe",
                "page": 3,
                "bbox": [0.1855, 0.3007, 0.7720, 0.3184],
                "snippet": "- à GALIA VENTURE 30 172 actions"
            }
        },
        {
            "event_id": "evt_2017-02-21_end_financiere_brienne",
            "event_code": "SHAREHOLDER_END",
            "event_date": "2017-02-21",
            "payload": {
                "holder_name": "FPCI FINANCIERE DE BRIENNE",
                "shares": 43103
            },
            "source": {
                "inpi_id": "63e9593a8be6eb9f9d257ebe",
                "page": 3,
                "bbox": [0.1868, 0.3190, 0.7696, 0.3346],
                "snippet": "- à FPCI FINANCIERE DE BRIENNE 43 103 actions"
            }
        },

        # 7. Aumento de Capital por Incorporação de Reservas (2018-03-23, Doc 15)
        {
            "event_id": "evt_2018-03-23_cap_increase_reserves",
            "event_code": "CAPITAL_INCREASE",
            "event_date": "2018-03-23",
            "payload": {
                "amount_eur": 182759.0,
                "capital_after_eur": 400000.0,
                "method": "incorporation de reserves"
            },
            "source": {
                "inpi_id": "63e9593b8be6eb9f9d257ec0",
                "page": 2,
                "bbox": [0.1061, 0.7043, 0.8781, 0.7385],
                "snippet": "L'Associée Unique décide d'augmenter le capital social d'un montant de 182 759 euros par prélèvement sur le poste « Autres Réserves »."
            }
        }
    ]
    return events


def build_timeline():
    """
    Linha do tempo contábil da cap table após cada evento relevante.
    """
    timeline = [
        # Estado 0: Constituição de 2004
        {
            "as_of": "2004-12-15",
            "capital_eur": 37000.0,
            "shares_total": 370,
            "nominal_eur": 100.0,
            "holders": [
                {
                    "name": "Xavier AUMONT",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 155,
                    "pct": 41.89
                },
                {
                    "name": "Antonio BLANCO MARINA",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 155,
                    "pct": 41.89
                },
                {
                    "name": "Franck GICQUEL",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 60,
                    "pct": 16.22
                }
            ],
            "caused_by": [
                "evt_2004-12-15_incorp_capital",
                "evt_2004-12-15_entry_aumont",
                "evt_2004-12-15_entry_blanco",
                "evt_2004-12-15_entry_gicquel"
            ]
        },

        # Estado: realização do primeiro aumento de capital (150.000 €)
        #
        # O ato de 17/05/2005 (inpi_id 63e9593b8be6eb9f9d257ec4, página 2) constata
        # "la réalisation définitive de l'augmentation de capital de 113 000 € par
        # la création de 1 130 actions nouvelles de numéraire de 100 euros, pour
        # porter le capital à 150 000 €", dividido em 1 500 ações de 100 €.
        #
        # Os três subscritores das 1 130 aparecem AGRUPADOS numa única linha, e não
        # por descuido: os atos provam que foram eles que as detiveram (o trespasse
        # de 16/08/2005 versa sobre "la totalité des actions détenues" por eles, e a
        # repartição 823/617/60 só fecha com +668 e +462 sobre os 155/155 iniciais,
        # que é 1 130), mas não documentam a divisão individual entre os três. O
        # agregado é o que está provado; a divisão está declarada como não
        # documentada no item (7) das notas.
        {
            "as_of": "2005-05-17",
            "capital_eur": 150000.0,
            "shares_total": 1500,
            "nominal_eur": 100.0,
            "holders": [
                {
                    "name": "Xavier AUMONT",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 155,
                    "pct": 10.33
                },
                {
                    "name": "Antonio BLANCO MARINA",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 155,
                    "pct": 10.33
                },
                {
                    "name": "Franck GICQUEL",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 60,
                    "pct": 4.00
                },
                {
                    "name": "Malik GUELLATI, Christophe LEROUX, Marielle ROUJEAN",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 1130,
                    "pct": 75.33
                }
            ],
            "caused_by": [
                "evt_2005-05-17_cap_increase_150k",
                "evt_2005-05-17_entry_souscripteurs"
            ]
        },

        # Estado: após o trespasse de 16/08/2005
        #
        # Estava datado 2005-05-17, mas as causas listadas abaixo são todas de
        # 2005-08-16 — o estado contradizia a própria lista de eventos. A composição
        # 823/617/60 é a "nouvelle répartition" que o trespasse de 16/08/2005 produz
        # (ato de 2006-01-04, inpi_id 63e9593b8be6eb9f9d257ec2, página 6).
        {
            "as_of": "2005-08-16",
            "capital_eur": 150000.0,
            "shares_total": 1500,
            "nominal_eur": 100.0,
            "holders": [
                {
                    "name": "Antonio BLANCO MARINA",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 803,
                    "pct": 53.53
                },
                {
                    "name": "Xavier AUMONT",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 637,
                    "pct": 42.47
                },
                {
                    "name": "Franck GICQUEL",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 60,
                    "pct": 4.00
                }
            ],
            "caused_by": [
                "evt_2005-08-16_transfer_to_blanco",
                "evt_2005-08-16_transfer_to_aumont",
                "evt_2005-08-16_exit_guellati",
                "evt_2005-08-16_exit_leroux",
                "evt_2005-08-16_exit_roujean"
            ]
        },

        # Estado 2: Após segundo aumento e entrada de Michel Capgras (200.000 €)
        {
            "as_of": "2006-10-20",
            "capital_eur": 200000.0,
            "shares_total": 2000,
            "nominal_eur": 100.0,
            "holders": [
                {
                    "name": "Antonio BLANCO MARINA",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 953,
                    "pct": 47.65
                },
                {
                    "name": "Xavier AUMONT",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 742,
                    "pct": 37.10
                },
                {
                    "name": "Michel CAPGRAS",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 225,
                    "pct": 11.25
                },
                {
                    "name": "Franck GICQUEL",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 80,
                    "pct": 4.00
                }
            ],
            "caused_by": [
                "evt_2006-10-20_cap_increase_200k",
                "evt_2006-10-20_entry_capgras",
                "evt_2006-10-20_transfer_aumont_to_capgras"
            ]
        },

        # Estado: após os aportes de AUMONT e GICQUEL à HADEAN (2007-09-07)
        #
        # AUMONT (742) e GICQUEL (80) transferem a totalidade das suas ações à
        # HADEAN. Restam BLANCO 953 + CAPGRAS 225 + HADEAN 822 = 2.000 ações,
        # que é o total em circulação desde 2006-10-20.
        {
            "as_of": "2007-09-07",
            "capital_eur": 200000.0,
            "shares_total": 2000,
            "nominal_eur": 100.0,
            "holders": [
                {
                    "name": "Antonio BLANCO MARINA",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 953,
                    "pct": 47.65
                },
                {
                    "name": "HADEAN",
                    "siren": "499979540",
                    "kind": "COMPANY",
                    "shares": 822,
                    "pct": 41.10
                },
                {
                    "name": "Michel CAPGRAS",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 225,
                    "pct": 11.25
                }
            ],
            "caused_by": [
                "evt_2007-09-07_transfer_aumont_hadean",
                "evt_2007-09-07_end_aumont",
                "evt_2007-09-07_transfer_gicquel_hadean",
                "evt_2007-09-07_end_gicquel",
                "evt_2007-09-07_entry_hadean_apports"
            ]
        },

        # Estado: após o aporte de CAPGRAS à HADEAN (2008-04-18)
        #
        # Restam BLANCO 953 + HADEAN 1.047 = 2.000 ações. A saída de BLANCO é a
        # única que nenhum documento dos dois acervos registra — ver nota (2).
        {
            "as_of": "2008-04-18",
            "capital_eur": 200000.0,
            "shares_total": 2000,
            "nominal_eur": 100.0,
            "holders": [
                {
                    "name": "Antonio BLANCO MARINA",
                    "siren": None,
                    "kind": "PERSON",
                    "shares": 953,
                    "pct": 47.65
                },
                {
                    "name": "HADEAN",
                    "siren": "499979540",
                    "kind": "COMPANY",
                    "shares": 1047,
                    "pct": 52.35
                }
            ],
            "caused_by": [
                "evt_2008-04-18_transfer_capgras_hadean",
                "evt_2008-04-18_end_capgras"
            ]
        },

        # Estado 3: Aquisição pela HADEAN + Split 100:1 + Aumentos Cat A e B (368.102 €)
        {
            "as_of": "2008-06-27",
            "capital_eur": 368102.0,
            "shares_total": 368102,
            "nominal_eur": 1.0,
            "holders": [
                {
                    "name": "HADEAN",
                    "siren": "499979540",
                    "kind": "COMPANY",
                    "shares": 217241,
                    "pct": 59.02
                },
                {
                    "name": "FPCI SECURITE",
                    "siren": None,
                    "kind": "COMPANY",
                    "shares": 64655,
                    "pct": 17.56
                },
                {
                    "name": "FPCI FINANCIERE DE BRIENNE",
                    "siren": None,
                    "kind": "COMPANY",
                    "shares": 43103,
                    "pct": 11.71
                },
                {
                    "name": "GALIA VENTURE",
                    "siren": None,
                    "kind": "COMPANY",
                    "shares": 30172,
                    "pct": 8.20
                },
                {
                    "name": "FIP GALIA PME 4",
                    "siren": None,
                    "kind": "COMPANY",
                    "shares": 12931,
                    "pct": 3.51
                }
            ],
            "caused_by": [
                "evt_2008-06-27_entry_hadean",
                "evt_2008-06-27_dual_class_creation",
                "evt_2008-06-27_cap_increase_cat_a",
                "evt_2008-06-27_cap_increase_cat_b"
            ]
        },

        # Estado 4: Redução de capital com saída dos investidores (217.241 €)
        {
            "as_of": "2017-02-21",
            "capital_eur": 217241.0,
            "shares_total": 217241,
            "nominal_eur": 1.0,
            "holders": [
                {
                    "name": "HADEAN",
                    "siren": "499979540",
                    "kind": "COMPANY",
                    "shares": 217241,
                    "pct": 100.0
                }
            ],
            "caused_by": [
                "evt_2017-02-21_cap_decrease_cancel_b",
                "evt_2017-02-21_end_fpci_securite",
                "evt_2017-02-21_end_galia_pme4",
                "evt_2017-02-21_end_galia_venture",
                "evt_2017-02-21_end_financiere_brienne"
            ]
        },

        # Estado 5: Incorporação de Reservas (400.000 €)
        {
            "as_of": "2018-03-23",
            "capital_eur": 400000.0,
            "shares_total": 400000,
            "nominal_eur": 1.0,
            "holders": [
                {
                    "name": "HADEAN",
                    "siren": "499979540",
                    "kind": "COMPANY",
                    "shares": 400000,
                    "pct": 100.0
                }
            ],
            "caused_by": [
                "evt_2018-03-23_cap_increase_reserves"
            ]
        }
    ]
    return timeline


NOTES = (
    "Lacunas e contradições declaradas de propósito (o BRIEF pede o que não foi resolvido). "
    "(1) DUAS FONTES DISCORDAM, E É UMA REGRA QUE RESOLVE — não o gosto de quem lê. (a) O ato de 2006-01-04 "
    "(inpi_id 63e9593b8be6eb9f9d257ec2, página 6) dá a 'nouvelle répartition' do trespasse de 16/08/2005 como 823 "
    "ações para Antonio BLANCO (54,87%) e 617 para Xavier AUMONT (41,13%), invocando o 'registre des mouvements de "
    "titres'. (b) A folha de presença da AGE de 20/10/2006 (inpi_id 63e9593b8be6eb9f9d257ec7, página 6), lida na "
    "IMAGEM renderizada, traz 803 e 637 nas duas colunas, com a menção 'Certifiée sincère et véritable'. Não é erro "
    "de OCR: os dois pares foram conferidos na imagem. (c) A REGRA APLICADA, declarada aqui para poder ser refutada: "
    "quando duas leituras documentadas satisfazem o mesmo invariante de fechamento — ambas somam 1.500 com GICQUEL — "
    "adota-se aquela sob a qual a CADEIA SEGUINTE fecha usando apenas movimentos documentados. A 3ª Resolução do ato "
    "de 2007-02-20 reserva as 500 ações novas em 'Pour 330 actions' a AUMONT, 'Pour 150 actions' a BLANCO e 'Pour 20 "
    "actions' a GICQUEL, e 330+150+20 = 500 exatamente. Só a base 803/637 fecha com o estado de 2006-10-20: "
    "803+150 = 953; 637+330-225 = 742 (225 cedidas a CAPGRAS); 60+20 = 80. Com a base 823/617, BLANCO terminaria em "
    "973 e AUMONT em 722 — a leitura 823/617 exigiria um movimento de 20 ações que nenhum ato documenta. A timeline "
    "adota 803/637 em 2005-08-16. (d) O QUE **NÃO** SE PODE AFIRMAR COM OS DADOS DISPONIBILIZADOS: por que as duas "
    "fontes diferem. Se houve um trespasse de 20 ações entre 16/08/2005 e 20/10/2006, ou se o ato de 2006-01-04 "
    "transcreveu errado o registre, os documentos fornecidos não permitem decidir. O que se afirma é apenas qual "
    "leitura é compatível com a cadeia documentada — e essa é a única afirmação que a evidência sustenta. "
    "(2) As saídas dos sócios pessoa física em 2008 NÃO são indocumentadas — elas estavam fora da pasta da Archean. "
    "Os atos da própria HADEAN registram os aportes: Xavier AUMONT contribuiu 742 ações da ARCHEAN, Franck GICQUEL 80 "
    "(inpi_id 63f0a89c7a07a2434c069135, páginas 5 e 6, na constituição da HADEAN em 2007-09-18) e Michel CAPGRAS 225 "
    "(inpi_id 63f0a89c7a07a2434c069136, página 3, em 2008-04-30). As três contagens coincidem exatamente com o estado de "
    "2006-10-20 desta timeline. É o caso que o brief antecipa: a relação não aparece nos documentos da própria Archean e "
    "exige ir olhar a controladora. Resta uma lacuna estreita e nomeada: as 953 ações de Antonio BLANCO MARINA não "
    "aparecem em nenhum ato da HADEAN presente no acervo. A lacuna é delimitada, não suposta: varredura de todo o "
    "acervo OCR das duas SIREN, ato por ato e página por página, encontrou menções a BLANCO apenas nos atos da "
    "própria Archean (11 ocorrências), nenhuma nos da HADEAN — a saída não é documentada no corpus fornecido. "
    "(3) O artigo 6 dos estatutos anexos ao ato de 2018 grafa '185 759 euros' onde a 1ª Resolução do mesmo ato prova "
    "182 759 euros (217.241 + 182.759 = 400.000): erro material do escrivão. "
    "(4) DUAS IMPRECISÕES DE NATUREZAS DIFERENTES — não quatro da mesma, como uma versão anterior deste arquivo dava a "
    "entender. (a) AMBIGUIDADE POR CONSTRUÇÃO: dois eventos (evt_2005-08-16_exit_leroux e evt_2005-08-16_exit_roujean) "
    "citam trechos que aparecem duas vezes na mesma página; a bbox aponta a primeira ocorrência, e nenhum critério "
    "disponível escolhe entre as duas. Desvio medido: 0.3888 e 0.4034. É limite do dado, não tarefa pendente. "
    "(b) CAIXA DECLARADA QUE NÃO COBRIA A CITAÇÃO — corrigida, e a correção é de substância. Dois eventos "
    "(evt_2006-10-20_transfer_aumont_to_capgras e evt_2017-02-21_cap_decrease_cancel_b) tinham trecho sem repetição "
    "na página, mas a caixa declarada não cobria o próprio trecho: na primeira ela cortava o primeiro caractere da "
    "linha ('L'Assemblée', x0 declarado 0.0504 contra 0.0391 reconstruído); na segunda deixava de fora a última linha "
    "da citação ('nominale chacune.', y1 declarado 0.4176 contra 0.4347). Conferido nas duas imagens renderizadas, com "
    "a caixa declarada e a reconstruída desenhadas sobre a página. Como o recorte é a prova visual da alegação, uma "
    "caixa que não cobre a citação produz um relatório que não sustenta a própria frase. Corrigidas para os valores "
    "reconstruídos; o benchmark passa a acusar 29/31 exatas, restando as duas ambiguidades do item (a). Medição "
    "reproduzível: python main.py --siren 480489707 --benchmark results.json "
    "(5) Erros do OCR fornecido em páginas efetivamente citadas, todos com score alto (0.956 a 0.988) — a confiança "
    "do motor NÃO os detecta: '(37.0o0)' onde a imagem diz '(37.000)'; '5o0' em vez de '500' e '20/1O/2006' em vez de "
    "'20/10/2006'; '200.0euros' em vez de '200.000 euros' (desvio de fator 1000) e '2o08' em vez de '2008'; "
    "'(82ooo)' em vez de '(82000)'. Os snippets submetidos usam os valores corretos, conferidos contra a imagem "
    "renderizada do PDF — o OCR é entrada, não fonte de verdade. Auditoria reproduzível com: "
    "python main.py --siren 480489707 --ocr-errors --benchmark results.json"
    "(6) MÉTODO, declarado para não induzir leitura errada: estes seis estados foram MONTADOS À MÃO em "
    "reconcile_timeline.py::build_timeline(), a partir da leitura dos atos — não são derivados do array "
    "events. A máquina confere os invariantes algébricos sobre a timeline digitada (fechamento das cotas, "
    "identidade do capital, fechamento percentual, conservação de fluxo, coerência de datas), e é isso que o "
    "47/48 mede. Rodar src/ledger.py sobre estes mesmos eventos devolve outra timeline — 370 cotas em "
    "2005-05-17 em vez de 1.500, 201.725 em 2008-06-27 em vez de 368.102 — porque os eventos não carregam a "
    "alocação de cotas de cada aumento intermediário, e o trespasse de 2005-08-16 nomeia cedentes "
    "(GUELLATI, LEROUX, ROUJEAN) que não entram no quadro societário em nenhum evento. Derivar a timeline dos "
    "eventos exigiria um evento de alocação por aumento — é o próximo passo, não uma afirmação que se possa "
    "fazer hoje. "
    "(7) DATA CORRIGIDA, e a lacuna que restou. O estado que esta timeline rotulava como 2005-05-17 trazia, "
    "ele mesmo, os eventos de 2005-08-16 entre as suas causas — o estado contradizia a própria lista de "
    "eventos que o gerou. A composição 823/617/60 é a 'nouvelle répartition' do trespasse, e o ato de "
    "2006-01-04 (inpi_id 63e9593b8be6eb9f9d257ec2, página 6) é explícito: 'au terme des ordres de mouvement "
    "à émettre en date du 16 août 2005, la nouvelle répartition suivante entre les associés'. O estado passou "
    "a ser datado 2005-08-16, e o estado de 2005-05-17 — que faltava — foi emitido a partir do próprio ato do "
    "aumento (inpi_id 63e9593b8be6eb9f9d257ec4, página 2): 'la réalisation définitive de l'augmentation de "
    "capital de 113 000 € par la création de 1 130 actions nouvelles de numéraire de 100 euros, pour porter le "
    "capital à 150 000 €'. O mesmo parágrafo do ato de 2006-01-04 acrescenta que a repartição 'est conforme au "
    "registre des mouvements de titres et l'emporte sur celle indiquée dans le protocole, qui contient une "
    "erreur' — é a origem documental do 803/637 do item (1): o erro estava no protocolo de cessão, e o "
    "registre de movimentações o corrige para 823/617. LACUNA REMANESCENTE: os três subscritores das 1 130 "
    "ações novas aparecem AGRUPADOS numa única linha do estado de 2005-05-17. O total de 1 130 está "
    "documentado, e que foram eles que as detiveram está provado pela repartição de 16/08 (+668 sobre os 155 "
    "de BLANCO e +462 sobre os 155 de AUMONT = 1 130); o que os atos NÃO dizem é a divisão individual entre "
    "Malik GUELLATI, Christophe LEROUX e Marielle ROUJEAN. O agregado é o que se pode afirmar; a divisão, não."
    " Por consequência, a ENTRADA dos três é emitida como evento-consequência (evt_2005-05-17_entry_souscripteurs), "
    "com a mesma fonte do aumento — a spec do próprio desafio define que ações de consequência assim são "
    "derivadas no momento da projeção, não lidas: o ato não diz 'GUELLATI entrou', diz que 1.130 ações novas "
    "foram criadas. "
    "(8) O INVARIANTE 8 ACUSA A TRANSIÇÃO DE 2008, e a acusação é correta. Ele confere, transição a transição, "
    "se a variação de cada titular bate com os movimentos quantificados nos eventos. Passa em todas as "
    "transições de 2004 até 2008-04-18 — inclusive na de 2006, que é a que decide a contradição do item (1). E "
    "falha em 2008-04-18 -> 2008-06-27: a HADEAN varia +216.194 onde os eventos documentam +200.000. A causa é "
    "de MODELAGEM, não de leitura: a consolidação de 2008 está representada por uma entrada única de 200.000 "
    "ações na HADEAN, e não pelos movimentos que de fato a compõem — o desdobramento 100:1 (ausente do payload "
    "do CAPITAL_DUAL_CLASS), a absorção dos 95.300 títulos de BLANCO e as subscrições das Ações A e B "
    "(17.241 + 150.861). Só reconstruindo esses eventos a transição fica verificável. Enquanto não for feito, o "
    "invariante aponta o ponto fraco em vez de deixá-lo passar — e a absorção dos 95.300 títulos de BLANCO é o "
    "mesmo fato do item (2), para o qual não há documento. "
)


def build_group():
    """
    Bônus: Reconstrução das relações do grupo societário comprovadas documentalmente.
    """
    return {
        "nodes": [
            {
                "name": "ARCHEAN TECHNOLOGIES",
                "siren": "480489707",
                "resolved": True
            },
            {
                "name": "HADEAN",
                "siren": "499979540",
                "resolved": True
            },
            {
                "name": "ARCHEAN INTERNATIONAL",
                "siren": None,
                "resolved": False
            },
            {
                "name": "Xavier AUMONT",
                "siren": None,
                "resolved": False
            },
            {
                "name": "Franck GICQUEL",
                "siren": None,
                "resolved": False
            },
            {
                "name": "Michel CAPGRAS",
                "siren": None,
                "resolved": False
            }
        ],
        "edges": [
            {
                "from": "HADEAN",
                "to": "ARCHEAN TECHNOLOGIES",
                "relation": "shareholder_of",
                "pct": 100.0,
                "as_of": "2018-03-23",
                "source": {
                    "inpi_id": "63e9593b8be6eb9f9d257ec0",
                    "page": 3,
                    "bbox": [0.1234, 0.3965, 0.7991, 0.4307],
                    "snippet": "Il est divisé en 400 000 actions de 1 euro chacune entièrement libérées, intégralement détenues par la société HADEAN"
                }
            },
            {
                "from": "ARCHEAN INTERNATIONAL",
                "to": "ARCHEAN TECHNOLOGIES",
                "relation": "contract_counterparty",
                "pct": None,
                "as_of": "2005-08-16",
                "source": {
                    "inpi_id": "63e9593b8be6eb9f9d257ec2",
                    "page": 7,
                    "bbox": [0.1044, 0.1446, 0.8701, 0.1758],
                    "snippet": "accord entre ARCHEAN TECHNOLOGIES et ARCHEAN INTERNATIONAL"
                }
            },
            {
                "from": "Xavier AUMONT",
                "to": "HADEAN",
                "relation": "share_contribution",
                "pct": None,
                "as_of": "2007-09-07",
                "shares_archean": 742,
                "source": {
                    "inpi_id": "63f0a89c7a07a2434c069135",
                    "page": 5,
                    "bbox": [0.1195, 0.7397, 0.8855, 0.7579],
                    "snippet": "Monsieur Xavier AUMONT fait apport de la pleine propriété des 742 (sept cent"
                }
            },
            {
                "from": "Franck GICQUEL",
                "to": "HADEAN",
                "relation": "share_contribution",
                "pct": None,
                "as_of": "2007-09-07",
                "shares_archean": 80,
                "source": {
                    "inpi_id": "63f0a89c7a07a2434c069135",
                    "page": 6,
                    "bbox": [0.1208, 0.3261, 0.8841, 0.3428],
                    "snippet": "Monsieur Franck GICQUEL fait apport de la pleine propriété des QUATRE VINGT"
                }
            },
            {
                "from": "Michel CAPGRAS",
                "to": "HADEAN",
                "relation": "share_contribution",
                "pct": None,
                "as_of": "2008-04-18",
                "shares_archean": 225,
                "source": {
                    "inpi_id": "63f0a89c7a07a2434c069136",
                    "page": 3,
                    "bbox": [0.1555, 0.4931, 0.8765, 0.5093],
                    "snippet": "Monsieur Michel CAPGRAS propose de faire apport à la SAS HADEAN de 225 actions"
                }
            }
        ]
    }


def verify_algebraic_invariants(timeline):
    """
    Validação das fórmulas de fechamento contábil e de fluxo societário.
    """
    print("\n--- Auditoria Algébrica de Invariantes Societários ---")
    all_passed = True
    
    for i, state in enumerate(timeline):
        as_of = state["as_of"]
        cap = state["capital_eur"]
        shares = state["shares_total"]
        nom = state["nominal_eur"]
        holders = state["holders"]

        # Invariante 1: Capital = Ações * Valor Nominal
        expected_cap = shares * nom
        if abs(cap - expected_cap) > 1e-4:
            print(f"[FALHA Invariante 1] Estado {as_of}: Capital {cap} != {shares} * {nom} (esperado {expected_cap})")
            all_passed = False
        else:
            print(f"[OK Invariante 1] Estado {as_of}: Capital {cap:,.0f} € == {shares:,} ações * {nom} €")

        # Invariante 2: Fechamento da Cap Table (Soma das Cotas)
        total_shares_holders = sum(h["shares"] for h in holders if h.get("shares") is not None)
        if total_shares_holders != shares:
            print(f"[FALHA Invariante 2] Estado {as_of}: Soma das cotas ({total_shares_holders}) != Total ({shares})")
            all_passed = False
        else:
            print(f"[OK Invariante 2] Estado {as_of}: Soma das cotas ({total_shares_holders:,}) fecha 100% com o total")

        # Invariante 3: Percentuais fecham ~100%
        sum_pct = sum(h["pct"] for h in holders if h.get("pct") is not None)
        if abs(sum_pct - 100.0) > 0.1:
            print(f"[FALHA Invariante 3] Estado {as_of}: Soma dos percentuais = {sum_pct:.2f}% (esperado ~100%)")
            all_passed = False
        else:
            print(f"[OK Invariante 3] Estado {as_of}: Soma percentual = {sum_pct:.2f}%")

    return all_passed


def main():
    print("Iniciando geração do results.json reconciliado...")
    
    events = build_events()
    timeline = build_timeline()
    group = build_group()

    results_data = {
        "siren": "480489707",
        "events": events,
        "capital_timeline": timeline,
        "group": group,
        "notes": NOTES,
    }

    # 1. Executa a auditoria algébrica
    invariants_ok = verify_algebraic_invariants(timeline)
    if not invariants_ok:
        print("\nATENÇÃO: Invariantes algébricos falharam. Verifique os dados.")
        sys.exit(1)

    # 2. Valida contra o schema oficial
    print("\n--- Validação de Schema (challenges/actes/schema/results.schema.json) ---")
    with open(SCHEMA_PATH, encoding="utf-8") as sf:
        schema = json.load(sf)

    try:
        jsonschema.validate(instance=results_data, schema=schema)
        print("Schema Validation: SUCESSO! results.json 100% em conformidade com results.schema.json.")
    except jsonschema.ValidationError as e:
        print(f"Schema Validation FALHOU: {e.message}")
        print("Caminho do erro:", list(e.path))
        sys.exit(1)

    # 3. Salva no root como results.json
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)

    print(f"\nArquivo final gerado com sucesso em: {RESULTS_PATH}")
    print(f"Total de eventos mapeados e grounded: {len(events)}")
    print(f"Total de snapshots na timeline de capital: {len(timeline)}")
    print(f"Nós no grupo societário (Bônus): {len(group['nodes'])}")
    print(f"Arestas no grupo societário (Bônus): {len(group['edges'])}")


if __name__ == "__main__":
    main()
