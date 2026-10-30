"""Gera definições PBIP/PBIR editáveis. Não depende de plugins visuais."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PBI = ROOT / 'powerbi'
REPORT = PBI / 'PipelineWatch.Report'
MODEL = PBI / 'PipelineWatch.SemanticModel'
BASE = 'https://developer.microsoft.com/json-schemas/fabric/'
VC = BASE + 'item/report/definition/visualContainer/2.0.0/schema.json'
BG, PANEL, TEXT, MUTED, TEAL, AMBER, RED = '#0C1424', '#142238', '#E6EDF7', '#A3B5CE', '#38D6BD', '#F4BA62', '#F57883'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def literal(value):
    if isinstance(value, bool):
        encoded = str(value).lower()
    elif isinstance(value, (int, float)):
        encoded = f'{value}D'
    else:
        encoded = "'" + value.replace("'", "''") + "'"
    return {'expr': {'Literal': {'Value': encoded}}}


def fill(color):
    return {'solid': {'color': literal(color)}}


def prop(**kwargs):
    return [{'properties': kwargs}]


def binding(table, name, measure=False):
    return {'Measure' if measure else 'Column': {'Expression': {'SourceRef': {'Entity': table}}, 'Property': name}}


def projection(table, name, measure=False):
    return {'field': binding(table, name, measure), 'queryRef': f'{table}.{name}', 'nativeQueryRef': name}


def chrome(title=None, background=PANEL):
    vco = {'background': prop(show=literal(background is not None), color=fill(background or BG), transparency=literal(0)),
           'border': prop(show=literal(False)), 'visualHeader': prop(show=literal(False)),
           'padding': prop(**{k: literal(12) for k in ('top', 'bottom', 'left', 'right')}),
           'title': prop(show=literal(title is not None), text=literal(title or ''), fontColor=fill(TEXT), fontSize=literal(12), alignment=literal('left'))}
    return vco


class Page:
    def __init__(self, name, label, subtitle):
        self.path = REPORT / 'definition/pages' / name
        self.count = 0
        save(self.path / 'page.json', {'$schema': BASE + 'item/report/definition/page/2.0.0/schema.json',
             'name': name, 'displayName': label, 'displayOption': 'FitToPage', 'height': 800, 'width': 1440,
             'objects': {'background': prop(color=fill(BG), transparency=literal(0)),
                         'outspace': prop(color=fill(BG), transparency=literal(0))}})
        self.text(32, 20, 700, 45, 'PIPELINE / WATCH', 28, TEXT)
        self.text(34, 68, 1160, 30, subtitle, 13, MUTED)
        self.text(1180, 32, 228, 36, 'SYNTHETIC DATA  /  LAB', 11, TEAL)
        self.text(32, 768, 1376, 28, 'ENGENHARIA ELETROELETRÔNICA  •  Empresa, lotes e medições fictícios  •  Clique nos gráficos para filtrar', 11, MUTED)

    def visual(self, kind, x, y, w, h, objects=None, query=None, vco=None):
        self.count += 1
        name = f'v{self.count:019d}'
        visual = {'visualType': kind, 'drillFilterOtherVisuals': True, 'visualContainerObjects': vco if vco is not None else chrome()}
        if objects:
            visual['objects'] = objects
        if query:
            visual['query'] = {'queryState': query}
        save(self.path / 'visuals' / name / 'visual.json', {'$schema': VC, 'name': name,
             'position': {'x': x, 'y': y, 'width': w, 'height': h, 'z': self.count * 1000, 'tabOrder': self.count * 1000}, 'visual': visual})

    def text(self, x, y, w, h, text, size=14, color=TEXT):
        container = chrome(background=None)
        container['padding'] = prop(**{k: literal(0) for k in ('top', 'bottom', 'left', 'right')})
        self.visual('textbox', x, y, w, h, {'general': prop(paragraphs=[{'textRuns': [{'value': text,
                    'textStyle': {'fontFamily': 'Segoe UI', 'fontSize': f'{size}px', 'color': color}}]}])}, vco=container)

    def card(self, x, y, w, h, measure, color=TEAL):
        value_color = fill(color)
        if measure.endswith(' · saídas'):
            value_color = {'solid': {'color': {'expr': binding('Runs', measure.replace(' · saídas', ' · cor'), True)}}}
        self.visual('card', x, y, w, h,
                    {'labels': prop(color=value_color, fontSize=literal(30), labelDisplayUnits=literal(1)),
                     'categoryLabels': prop(show=literal(True), color=fill(MUTED), fontSize=literal(11))},
                    {'Values': {'projections': [projection('Runs', measure, True)]}})

    def slicer(self, x, y, w, column, title, table='Runs'):
        self.visual('slicer', x, y, w, 84,
                    {'data': prop(mode=literal('Dropdown')), 'header': prop(show=literal(True), text=literal(title), fontColor=fill(MUTED), textSize=literal(11)),
                     'items': prop(fontColor=fill(TEXT), background=fill(PANEL), textSize=literal(11)),
                     'selection': prop(singleSelect=literal(False), selectAllCheckboxEnabled=literal(True))},
                    {'Values': {'projections': [projection(table, column)]}}, chrome())

    def chart(self, kind, x, y, w, h, table, category, measures, title):
        cat = projection(table, category)
        cat['active'] = True
        self.visual(kind, x, y, w, h,
                    {'categoryAxis': prop(labelColor=fill(MUTED), showAxisTitle=literal(False), fontSize=literal(10)),
                     'valueAxis': prop(labelColor=fill(MUTED), showAxisTitle=literal(False), fontSize=literal(10), gridlineColor=fill('#25374E')),
                     'legend': prop(show=literal(len(measures) > 1), labelColor=fill(MUTED), position=literal('Top')),
                     'dataPoint': [{'properties': {'fill': fill([TEAL, RED, AMBER][i % 3])}, 'selector': {'metadata': 'Runs.' + m}} for i, m in enumerate(measures)]},
                    {'Category': {'projections': [cat]}, 'Y': {'projections': [projection('Runs', m, True) for m in measures]}}, chrome(title))

    def arrow(self, x, y, w, h, color=TEAL):
        container = chrome(background=None)
        container['padding'] = prop(**{k: literal(0) for k in ('top', 'bottom', 'left', 'right')})
        self.visual('shape', x, y, w, h,
                    {'shape': prop(tileShape=literal('arrow')),
                     'fill': [{'properties': {'fillColor': fill(color), 'transparency': literal(0)}, 'selector': {'id': 'default'}}],
                     'outline': [{'properties': {'show': literal(False)}, 'selector': {'id': 'default'}}]}, vco=container)


def build():
    save(PBI / 'PipelineWatch.pbip', {'$schema': BASE + 'pbip/pbipProperties/1.0.0/schema.json', 'version': '1.0',
         'artifacts': [{'report': {'path': 'PipelineWatch.Report'}}], 'settings': {'enableAutoRecovery': True}})
    save(REPORT / 'definition.pbir', {'$schema': BASE + 'item/report/definitionProperties/2.0.0/schema.json',
         'version': '4.0', 'datasetReference': {'byPath': {'path': '../PipelineWatch.SemanticModel'}}})
    save(REPORT / 'definition/version.json', {'$schema': BASE + 'item/report/definition/versionMetadata/1.0.0/schema.json', 'version': '2.0.0'})
    theme = {'name': 'PipelineWatch', 'dataColors': [TEAL, RED, AMBER, '#779AFF', '#B08EFF', '#6BC8E6'],
             'background': PANEL, 'foreground': TEXT, 'tableAccent': TEAL,
             'textClasses': {'label': {'color': MUTED, 'fontFace': 'Segoe UI'}, 'title': {'color': TEXT, 'fontFace': 'Segoe UI Semibold'},
                             'callout': {'color': TEAL, 'fontFace': 'Segoe UI Semibold'}}}
    save(REPORT / 'StaticResources/RegisteredResources/PipelineWatch.json', theme)
    save(REPORT / 'definition/report.json', {'$schema': BASE + 'item/report/definition/report/3.1.0/schema.json',
         'themeCollection': {'baseTheme': {'name': 'CY24SU06', 'reportVersionAtImport': {'visual': '1.8.50', 'page': '2.0.0', 'report': '3.0.0'}, 'type': 'SharedResources'},
                             'customTheme': {'name': 'PipelineWatch', 'reportVersionAtImport': {'visual': '1.8.50', 'page': '2.0.0', 'report': '3.0.0'}, 'type': 'RegisteredResources'}},
         'resourcePackages': [{'name': 'RegisteredResources', 'type': 'RegisteredResources', 'items': [{'name': 'PipelineWatch', 'path': 'PipelineWatch.json', 'type': 'CustomTheme'}]}],
         'settings': {'useStylableVisualContainerHeader': True, 'defaultFilterActionIsDataFilter': True, 'defaultDrillFilterOtherVisuals': True}})
    save(REPORT / 'definition/pages/pages.json', {'$schema': BASE + 'item/report/definition/pagesMetadata/1.0.0/schema.json',
         'pageOrder': ['overview', 'quality', 'flow'], 'activePageName': 'overview'})

    measures = {
        'Execuções': ('COALESCE(COUNTROWS(Runs),0)', '#,0'),
        'Recebidos': ('SUM(Runs[input_rows])', '#,0'),
        'Aprovados': ('SUM(Runs[accepted_rows])', '#,0'),
        'Rejeitados': ('SUM(Runs[rejected_rows])', '#,0'),
        'Qualidade': ('DIVIDE([Aprovados], [Recebidos])', '0.0%'),
        'Falhas': ('COALESCE(CALCULATE(COUNTROWS(Runs), KEEPFILTERS(Runs[status] = "Falha")),0)', '#,0'),
        'Alertas': ('COALESCE(CALCULATE(COUNTROWS(Runs), KEEPFILTERS(Runs[status] = "Alerta")),0)', '#,0'),
        'Ocorrências': ('COALESCE(COUNTROWS(Errors),0)', '#,0'),
        'Duração simulada (s)': ('DIVIDE(AVERAGE(Runs[duration_ms]),1000)', '0.00 "s"'),
        'Rejeição': ('DIVIDE([Rejeitados], [Recebidos])', '0.0%'),
    }
    for stage in ('Gerar', 'Bronze', 'Validar', 'Silver', 'Gold', 'Quarentena'):
        measures[stage + ' · saídas'] = (f'CALCULATE(SUM(Events[output_rows]), Events[stage_name] = "{stage}")', '#,0')
        measures[stage + ' · cor'] = (f'VAR F = CALCULATE(COUNTROWS(Events), Events[stage_name]="{stage}", Events[status]="Falha") '
                                      f'VAR A = CALCULATE(COUNTROWS(Events), Events[stage_name]="{stage}", Events[status]="Alerta") '
                                      f'VAR I = CALCULATE(COUNTROWS(Events), Events[stage_name]="{stage}", Events[status]="Ignorada") '
                                      f'VAR N = CALCULATE(COUNTROWS(Events), Events[stage_name]="{stage}") '
                                      f'RETURN SWITCH(TRUE(), F>0,"{RED}", A>0,"{AMBER}", I=N,"{MUTED}","{TEAL}")', '')
    columns = {
        'Runs': ('runs', 'run_id,event_date,created_at,pipeline_name,component_family,plant,scenario,seed,status,input_rows,accepted_rows,rejected_rows,error_count,duration_ms,measured_ms,quality_pct'),
        'Events': ('events', 'run_id,stage_name,stage_index,status,input_rows,output_rows,rejected_rows,duration_ms,event_date,pipeline_name,component_family,plant,run_status'),
        'Errors': ('errors', 'error_id,run_id,row_number,record_id,rule_name,field,message,event_date,pipeline_name,component_family,plant,run_status'),
        'Components': ('components', 'code,name,family,nominal_voltage')}
    integers = {'seed', 'input_rows', 'accepted_rows', 'rejected_rows', 'error_count', 'stage_index', 'output_rows', 'error_id', 'row_number'}
    decimals = {'duration_ms', 'measured_ms', 'quality_pct', 'nominal_voltage'}
    tables = []
    for table, (endpoint, names) in columns.items():
        names = names.split(',')
        types = {c: 'int64' if c in integers else 'double' if c in decimals else 'dateTime' if c == 'event_date' else 'string' for c in names}
        conversions = ', '.join('{"' + c + '", ' + {'int64': 'Int64.Type', 'double': 'type number', 'dateTime': 'type date', 'string': 'type text'}[t] + '}' for c, t in types.items())
        expression = ['let', f'    Source = Csv.Document(Web.Contents(ApiBaseUrl, [RelativePath="api/powerbi/{endpoint}"]), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
                      '    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
                      '    Typed = Table.TransformColumnTypes(Headers, {' + conversions + '}, "en-US")', 'in', '    Typed']
        item = {'name': table, 'columns': [{'name': c, 'dataType': t, 'sourceColumn': c, 'summarizeBy': 'none', **({'formatString': 'dd/MM/yyyy'} if t == 'dateTime' else {})} for c, t in types.items()],
                'partitions': [{'name': table, 'mode': 'import', 'source': {'type': 'm', 'expression': expression}}]}
        if table == 'Runs':
            item['measures'] = [{'name': n, 'expression': e, 'formatString': f} for n, (e, f) in measures.items()]
        tables.append(item)
    save(MODEL / 'definition.pbism', {'$schema': BASE + 'item/semanticModel/definitionProperties/1.0.0/schema.json', 'version': '1.0', 'settings': {}})
    save(MODEL / 'model.bim', {'name': 'PipelineWatch', 'compatibilityLevel': 1601, 'model': {'culture': 'pt-BR',
         'defaultPowerBIDataSourceVersion': 'powerBI_V3', 'tables': tables,
         'expressions': [{'name': 'ApiBaseUrl', 'kind': 'm', 'expression': '"http://127.0.0.1:5088" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
         'relationships': [{'name': 'Runs_' + t, 'fromTable': t, 'fromColumn': 'run_id', 'toTable': 'Runs', 'toColumn': 'run_id', 'crossFilteringBehavior': 'oneDirection'} for t in ('Events', 'Errors')],
         'annotations': [{'name': 'PBI_QueryOrder', 'value': '["ApiBaseUrl","Runs","Events","Errors","Components"]'}]}})

    page = Page('overview', '01 · Visão geral', '01 / VISÃO GERAL     Saúde das cargas de inspeção de componentes automotivos')
    page.slicer(32, 110, 435, 'component_family', 'Família do componente')
    page.slicer(485, 110, 435, 'plant', 'Unidade fictícia')
    page.slicer(938, 110, 470, 'status', 'Status da carga')
    for i, m in enumerate(('Execuções', 'Recebidos', 'Aprovados', 'Rejeitados', 'Qualidade')):
        page.card(32 + i * 279, 214, 260, 120, m, RED if m == 'Rejeitados' else TEAL)
    page.chart('lineChart', 32, 356, 880, 378, 'Runs', 'event_date', ['Aprovados', 'Rejeitados'], 'Volume por dia  /  histórico simulado')
    page.chart('clusteredBarChart', 934, 356, 474, 378, 'Runs', 'component_family', ['Aprovados'], 'Aprovados por família')

    page = Page('quality', '02 · Qualidade', '02 / QUALIDADE     Identifique as regras que desviaram registros para quarentena')
    page.slicer(32, 110, 435, 'component_family', 'Família do componente')
    page.slicer(485, 110, 435, 'plant', 'Unidade fictícia')
    page.slicer(938, 110, 470, 'status', 'Status da carga')
    for i, m in enumerate(('Rejeitados', 'Ocorrências', 'Rejeição', 'Falhas', 'Alertas')):
        page.card(32 + i * 279, 214, 260, 120, m, RED if i < 3 else AMBER)
    page.chart('clusteredBarChart', 32, 356, 880, 378, 'Errors', 'rule_name', ['Ocorrências'], 'Ocorrências por regra  /  um registro pode violar várias regras')
    page.chart('clusteredBarChart', 934, 356, 474, 378, 'Runs', 'component_family', ['Rejeitados'], 'Registros rejeitados por família')

    page = Page('flow', '03 · Fluxo do pipeline', '03 / FLUXO     Selecione uma execução para acompanhar suas conexões e saídas por etapa')
    page.slicer(32, 110, 900, 'run_id', 'Execução  /  limpe a seleção para visualizar o total')
    page.slicer(954, 110, 454, 'status', 'Status da carga')
    page.text(32, 215, 1320, 36, 'GERAÇÃO → INGESTÃO → VALIDAÇÃO → CURADORIA → CONSUMO', 18, TEXT)
    for i, stage in enumerate(('Gerar', 'Bronze', 'Validar', 'Silver', 'Gold')):
        x = 32 + i * 279
        page.card(x, 288, 238, 144, stage + ' · saídas')
        if i < 4:
            page.arrow(x + 243, 345, 31, 24)
    page.text(594, 443, 270, 44, '↓ rejeitados pela validação', 14, AMBER)
    page.card(590, 500, 238, 120, 'Quarentena · saídas', AMBER)
    page.card(32, 500, 238, 120, 'Falhas', RED)
    page.card(311, 500, 238, 120, 'Duração simulada (s)', MUTED)
    page.text(870, 496, 528, 132, 'As conexões representam o caminho dos dados. Os volumes respondem aos filtros. Uma falha na fonte ignora as etapas seguintes.\n\nDurações são simuladas, não um benchmark de produção.', 16, MUTED)
    page.text(32, 673, 1350, 62, 'CONSERVAÇÃO DE VOLUME   /   Recebidos = aprovados + rejeitados. Quarentena contém registros; ocorrências contabilizam violações de regras.', 15, TEXT)
    print('PBIP, modelo SQL-derived e 3 páginas PBIR gerados.')


if __name__ == '__main__':
    build()
