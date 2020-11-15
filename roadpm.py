# - coding: utf-8 --
"""
@info webpage to find patterns in traffic data
@author Francisco Neves
"""

import dash
import dash_core_components as dcc
import dash_html_components as html
import pandas as pd
from dash.dependencies import Input, Output
from pathlib import Path
import json
import statistics

from app import app
import map_utils
import gui_utils
import series_waze
import series_espiras
from roadpm_utils import Biclustering, get_pvalue_vs_area_figure, parameters_to_iluapp_layout, bicpams_parameters, \
    get_biclustering_vis, get_waze_events
from folium_draw import Draw

DOWNLOADS_PATH = str(Path(__file__).parent.parent.parent.parent) + '/data/temp/'


def get_multidrop_options(label_format, lst):
    return [{
        'label': label_format.format(str(el).capitalize()), 'value': el
    } for el in lst]


def get_graph(fig, title=None):
    children = []

    if title is not None:
        children.append(html.Div([html.H3(title, style={'marginBottom': 0})], style={'textAlign': "center"}))

    children.append(dcc.Graph(figure=fig))

    return html.Div(children)


def get_map():
    lisbon_map = map_utils.get_lisbon_map()
    Draw(page_prefix='padroes_rodovia',
         position='topleft',
         draw_options={'polyline': True, 'marker': True, 'circlemarker': False, 'circle': False, 'polygon': True,
                       'rectangle': False},
         edit_options={'poly': {'allowIntersection': False}}).add_to(lisbon_map)
    return lisbon_map


def embed_map(folium_map, prefix):
    return map_utils.embed_map(folium_map, prefix, height='370')


def get_all_method_params():
    params = [method_parameters[method] for method in method_parameters]
    res = []
    for param_list in params:
        res += param_list
    return res


pagetitle = 'Descrição: Padrões no trânsito rodoviário'
prefix = 'padroes_rodovia'

parameters = [
    ('date', ['2018-10-17', '2019-01-01'], gui_utils.Button.daterange),
    ('calendario', list(gui_utils.calendar.keys()) + list(gui_utils.week_days.keys()), gui_utils.Button.multidrop),
    ('granularidade_em_minutos', '60', gui_utils.Button.input),
    ('start_hour', '00:00', gui_utils.Button.input),
    ('end_hour', '23:59', gui_utils.Button.input),
    ('dataset', ['waze', 'espiras', 'integrative'], gui_utils.Button.radio),
    ('attributes', ['all'], gui_utils.Button.multidrop),
    ('geo_json', '', gui_utils.Button.input_hidden),
    ('series_cache', '', gui_utils.Button.input_hidden),
    ('method', 'biclustering', gui_utils.Button.input_hidden)
]
charts = [
    ('speed_series', gui_utils.get_null_label(), gui_utils.Button.html, True),
    ('time_point_series', gui_utils.get_null_label(), gui_utils.Button.html, True),
    ('prediction', gui_utils.get_null_label(), gui_utils.Button.html, True)
]

default_biclusters_options = ['no_biclusters_available_yet']
bics_plot_types = ['real_chart', 'discrete_chart', 'real_heatmap', 'discrete_heatmap']
method_parameters = {
    'biclustering_main': parameters_to_iluapp_layout(bicpams_parameters['main']) + [
        ('biclusters_plot', bics_plot_types,
         gui_utils.Button.radio),
        ('biclusters', default_biclusters_options, gui_utils.Button.multidrop),
        ('biclusters_cache', '', gui_utils.Button.input_hidden)
    ],
    'biclustering_optional': parameters_to_iluapp_layout(bicpams_parameters['optional'])
}

layout = gui_utils.get_layout(pagetitle, [('parameters', 27, parameters),
                                          ('selection_map', 27, [('lisbon_map', embed_map(get_map(), prefix),
                                                                  gui_utils.Button.html)]),
                                          ('method_parameters', 27, get_all_method_params(), 'empty_box'),
                                          ], charts, prefix=prefix)


def get_state_field(field: str, accessor: str = 'value', prefix: str = '', type=None):
    states = dash.callback_context.states
    value = states['{}{}.{}'.format(prefix, field, accessor)]
    if type:
        if type == dict:
            try:
                value = eval(value)
            except:
                return None
        else:
            value = type(value)
    return value


def biclustering_handler(speed_time_series, dataset):
    state_params = dash.callback_context.states
    # remove prefix and .value from
    params = {}
    for key in state_params:
        params[key.replace(prefix, '').replace('.value', '')] = state_params[key]

    method = Biclustering(speed_time_series, params, dataset)

    method_vis_figs = method.get_visualization()
    bics = method.discover_patterns()

    stat_vis = get_pvalue_vs_area_figure(bics)

    num_bics = len(bics)
    p_value_high = sum(float(x.get('pvalue')) > 0.01 for x in bics)
    p_value_interval = sum(0.1 >= float(x.get('pvalue')) >= 1e-3 for x in bics)
    p_value_low = sum(float(x.get('pvalue')) < 1e-3 for x in bics)
    num_rows_mean = statistics.mean([len(x['matrix']) for x in bics])
    num_rows_stdev = statistics.stdev([len(x['matrix']) for x in bics])
    num_cols_mean = statistics.mean([len(x['cols']) for x in bics])
    num_cols_stdev = statistics.stdev([len(x['cols']) for x in bics])

    return [html.Div(id=prefix + 'biclusters_container', style={'width': '40%'}),
            html.P(children='Num bics: {}'.format(num_bics)),
            html.P(children='p-value > 0.01: {}'.format(p_value_high)),
            html.P(children='p-value [1e-3, 0.1]: {}'.format(p_value_interval)),
            html.P(children='p-value < 1e-3: {}'.format(p_value_low)),
            html.P(children='Num rows mean: {}, standard deviation: {}'.format(
                num_rows_mean, num_rows_stdev)),
            html.P(children='Num columns mean: {}, standard deviation: {}'.format(
                num_cols_mean, num_cols_stdev))
            ] + [
               get_graph(stat_vis, 'Statistical Significance vs Area')] + [
               get_graph(fig, 'Heatmap - {}'.format(attribute.capitalize())) for
               fig, attribute in
               method_vis_figs], bics


def get_dataset_time_series(dataset, start_date, end_date, days, granularity):
    geojson = get_state_field('geo_json', prefix=prefix, type=dict)
    geojson = geojson['geometry'] if geojson else None

    all_series = []
    time_series = None
    locations = []
    if not geojson:
        return False, 'Selecione um ponto no mapa para obter eventos...'

    if dataset == 'waze' or dataset == 'integrative':
        events_per_street, events_locations = get_waze_events(start_date, end_date, geojson, days)
        events_locations = events_locations.rename(columns={'street_name': 'place_id'})
        events_locations = events_locations.rename(columns={'path.street_coord': 'location'})
        events_locations['dataset'] = 'waze'
        if events_per_street is None or events_per_street.empty:
            return False, 'Não foram encontrados eventos do waze com os filtros selecionados...'

        # Get time series
        time_series, name = series_waze.get_event_series(events_per_street, granularity, geojson)
        all_series.append(time_series)
        locations.append(events_locations)

    if dataset == 'espiras' or dataset == 'integrative':
        time_series, events_locations = series_espiras.get_spatial_series_per_loop(start_date, end_date, granularity,
                                                                                   days, geojson)
        events_locations = events_locations.rename(columns={'espira': 'place_id'})
        events_locations = events_locations.rename(columns={'coordinates': 'location'})
        events_locations['dataset'] = 'espiras'
        events_locations = events_locations.drop_duplicates('place_id')

        locations.append(events_locations)
        all_series.append(time_series)

    if dataset != 'integrative':
        return True, (time_series, locations[0])

    # Integrative
    if len(all_series) > 1:
        time_series = pd.merge(all_series[0], all_series[1], left_index=True, right_index=True)
        locations = pd.concat(locations)
    else:
        time_series = all_series[0]
        locations = locations[0]
    for attr in time_series.columns:
        if attr.startswith('speed'):
            time_series[attr] = time_series[attr].fillna(time_series[attr].max())
        elif attr.startswith('spatial_extension') or attr.startswith('delay'):
            time_series[attr] = time_series[attr].fillna(0)
        else:
            # espiras
            time_series[attr] = time_series[attr].fillna(0)

    return True, (time_series, locations)


@app.callback(
    Output(prefix + 'biclusters_container', 'children'),
    [Input(prefix + 'biclusters', 'value'), Input(prefix + 'biclusters_cache', 'value'),
     Input(prefix + 'biclusters_plot', 'value')])
def show_bicluster_plot(sel_bics, bics, plot_type, *args):
    if bics == '':
        return ''
    bics = json.loads(bics)

    figs = []
    for bic_i in sel_bics:
        if bic_i == 'no_biclusters_available_yet':
            break
        bic = bics[int(bic_i) - 1]
        fig = get_biclustering_vis(bic, plot_type, bics)
        figs.append(get_graph(fig, 'Bicluster {} - pvalue {:.4g}'.format(bic_i, float(bic['pvalue']))))
    return figs


@app.callback(
    Output(prefix + 'method_parameters', 'children'),
    [Input(prefix + 'method', 'value')])
def change_method(abordagem, *args):
    res = []
    for method in method_parameters:
        params = method_parameters[method]
        if method.startswith(abordagem):
            title = method.replace('_', ' ').capitalize() + ' Parameters'
            children = gui_utils.get_block_parameters(method + 'method_parameters', title, 27, params,
                                                      prefix=prefix)
        else:
            children = gui_utils.get_block_parameters(method + 'method_parameters', '', 27, params,
                                                      prefix=prefix, hidden=True)
        res.append(children)

    return res


@app.callback(
    [Output(prefix + 'charts', 'children'),
     Output(prefix + 'biclusters', 'options'),
     Output(prefix + 'attributes', 'options'),
     Output(prefix + 'biclusters_cache', 'value'),
     Output(prefix + 'series_cache', 'value')],
    [Input(prefix + 'button', 'n_clicks'), Input(prefix + 'attributes', 'value')],
    gui_utils.get_states(
        parameters + get_all_method_params(), False,
        prefix))
def run_discovery(n_clicks, attributes, *args):
    attributes_opts = []
    if not n_clicks:
        return [[], default_biclusters_options, attributes_opts, '', '']

    trigger = dash.callback_context.triggered[0]
    data_cached = False
    if 'button' in trigger['prop_id']:
        attributes = None
    else:
        data_cached = True

    # Date range
    start_date = pd.to_datetime(get_state_field('date', 'start_date', prefix))
    end_date = pd.to_datetime(get_state_field('date', 'end_date', prefix))

    # Days
    calendar = get_state_field('calendario', prefix=prefix)
    days = [gui_utils.get_calendar_days(calendar)]

    # Granularity
    granularity = get_state_field('granularidade_em_minutos', prefix=prefix, type=int)

    dataset = get_state_field('dataset', prefix=prefix, type=str)

    if not data_cached:
        params_ok, res = get_dataset_time_series(dataset, start_date, end_date, days, granularity)

        if not params_ok:
            res = html.Span(res)
            return [[res], default_biclusters_options, attributes_opts, '', '']

        time_series, locations = res
        time_series_orig = time_series
    else:
        # Read stuff from cached fields
        time_series_orig = pd.read_json(get_state_field('series_cache', prefix=prefix, type=str), orient='split')

        # Select only the columns of selected attributes
        if len(attributes) != 0:
            time_series = time_series_orig[attributes]
        else:
            time_series = time_series_orig

    start_hour = get_state_field('start_hour', prefix=prefix, type=str)
    end_hour = get_state_field('end_hour', prefix=prefix, type=str)

    time_series = time_series.between_time(start_hour, end_hour)
    filename = 'dataset_{}{}-{}{}-{}'.format(start_date, start_hour, end_date, end_hour, dataset)
    file_path = '{}/{}'.format(DOWNLOADS_PATH, filename)
    time_series_orig.between_time(start_hour, end_hour).to_csv('{}.csv'.format(file_path))

    if not data_cached:
        locations.to_csv('{}-locations.csv'.format(file_path))

    res, bics = biclustering_handler(time_series, dataset)
    bic_options = get_multidrop_options('Bicluster {}', range(1, len(bics) + 1))
    bics_cache = json.dumps(bics)

    time_series_attrs = list(time_series_orig.columns)
    time_series_attrs = get_multidrop_options('{}', time_series_attrs)

    attributes_opts += time_series_attrs

    return [res, bic_options, attributes_opts, bics_cache,
            time_series_orig.to_json(orient='split')]


if __name__ == '__main__':
    app.layout = layout
    app.run_server(debug=False, port=8051)
