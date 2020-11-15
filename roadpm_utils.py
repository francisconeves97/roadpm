import numpy as np
import plotly.graph_objects as go
import dash_html_components as html
import subprocess
import re
import hashlib
import gui_utils
from arff2pandas import a2p
import pandas as pd
import os

DOWNLOADS_PATH = str(os.path.abspath(os.path.dirname(__file__))) + '/data/'
JAR_DIRECTORY = str(os.path.dirname(__file__))


def get_waze_events(start_date, end_date, geojson, days):
    # implementation needs access to the data sources
    pass


def reshape_data(data):
    data = data.copy()
    data['Day'] = data.apply(lambda x: x.name.strftime('%Y-%m-%d'), axis=1)
    data['Hour'] = data.apply(lambda x: x.name.strftime('%H:%M'), axis=1)
    return data


def get_bics_max_and_min(bics, matrix_type):
    all_values = []
    for bic in bics:
        for k in bic[matrix_type]:
            for i in k:
                all_values.append(float(i))
    return min(all_values) - 1, max(all_values) + 1


def get_biclustering_vis(bic, type):
    matrix = 'real_matrix' if type.startswith('real') else 'matrix'

    if type.endswith('chart'):
        fig = go.Figure()

        for i, line in enumerate(bic[matrix]):
            fig.add_trace(go.Scatter(x=bic['cols'], y=line, name='row {}'.format(i)))

        fig.update_layout(showlegend=False)
    else:
        heatmap = go.Heatmap(
            z=bic[matrix],
            x=bic['cols'],
            y=list(range(len(matrix))),
            colorscale='OrRd')
        fig = go.Figure(data=heatmap)

    return fig


def get_pvalue_vs_area_figure(bics):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[bic['area'] for bic in bics], y=[bic['pvalue'] for bic in bics], mode='markers'))
    fig.update_layout(yaxis_type='log', xaxis_title='area', yaxis_title='pvalue')
    return fig


class Biclustering:
    def __init__(self, series, parameters, dataset):
        self.series = series
        self.transactions = reshape_data(series)
        self.reverse_scale_map = {
            'speed': True,
            'spatial_extension': False,
            'delay': False
        }
        self.bicpams_wrapper = BicPamsPyWrapper()
        self.parameters = parameters
        self.dataset = dataset
        self.context_cutpoints = None

    def get_visualization(self):
        if self.transactions.empty:
            return html.Span('Não foram encontrados congestionamentos para executar o modelo...')

        figs = []
        for attr in self.series.columns:
            values = self.transactions[attr]
            days = self.transactions['Day']
            hours = self.transactions['Hour']

            reverse_scale = False
            if self.dataset == 'waze' or self.dataset == 'integrative':
                for key in self.reverse_scale_map:
                    if attr.startswith(key):
                        reverse_scale = self.reverse_scale_map[key]

            heatmap = go.Heatmap(
                z=values,
                x=hours,
                y=days,
                colorscale='OrRd',
                reversescale=reverse_scale)
            fig = go.Figure(data=heatmap)
            figs.append((fig, attr))

        return figs

    def discover_patterns(self):
        arff_file = self.export_transactions()
        bics = self.bicpams_wrapper.run(arff_file, self.parameters)
        return bics

    def replace_missing_values(self, data, attribute):
        if attribute.startswith('speed'):
            val_to_replace = self.series[attribute].max()
        elif attribute.startswith('spatial_extension'):
            val_to_replace = 0
        elif attribute.startswith('delay'):
            val_to_replace = 0
        else:
            val_to_replace = 0

        return data.replace(val_to_replace, np.nan)

    def get_file_path(self):
        min_date, max_date = self.transactions['Day'].iloc[0], self.transactions['Day'].iloc[
            len(self.transactions.index) - 1]
        filename = 'biclustering_{}-{}-{}-{}'.format(min_date, max_date, self.dataset, hash_params(self.parameters))
        file_path = '{}{}'.format(DOWNLOADS_PATH, filename)
        return file_path

    def export_transactions(self):
        data = None
        for attr in self.series.columns:
            new_columns = self.transactions.pivot('Day', 'Hour', attr)
            new_columns = self.replace_missing_values(new_columns, attr)

            if self.dataset != 'integrative':
                if attr.startswith('speed') or attr.startswith('spatial_extension') or attr.startswith('delay'):
                    new_columns = new_columns.add_prefix('{}_'.format(attr))
                else:
                    new_columns = new_columns.add_suffix('_{}'.format(attr))
            else:
                new_columns = new_columns.add_suffix('_{}'.format(attr))
            if data is None:
                data = new_columns
            else:
                data = pd.concat([data, new_columns], axis=1, sort=False)
        file_path = self.get_file_path()
        # Reorder columns
        data = data.reindex(sorted(data.columns), axis=1)

        for hour in data.columns:
            data = data.rename(columns={hour: '{}@NUMERIC'.format(hour)})
        arff_file = '{}.arff'.format(file_path)
        with open(arff_file, 'w') as f:
            a2p.dump(data, f)

        return arff_file


def parse_string_list(string):
    res = []
    string = string.replace('[', '').replace(']', '')
    for val in string.split(','):
        res.append(val)
    return res


def parse_matrix(matrix):
    lines = matrix.split('\n')[:-3]
    return [line.split('\t')[1:] for line in lines]


bicpams_parameters = {
    'main': [
        {'name': 'coherency_assumption',
         'options': [
             'Constant',
             'OrderPreserving',
             'ConstantOverall',
             'Additive',
             'Multiplicative',
             'Symmetric'
         ]},
        {'name': 'coherency_strength', 'default': 3},
        {'name': 'quality', 'default': 70}
    ],
    'optional': [
        {'name': 'coherency_orientation',
         'options': [
             'PatternOnRows',
             'PatternOnColumns'
         ]},
        {'name': 'dissimilarity',
         'options': [
             'Elements',
             'Rows',
             'Columns'
         ]},
        {'name': 'min_bics', 'default': 100},
        {'name': 'min_columns', 'default': 4},
        {'name': 'num_iterations', 'default': 2},
        {'name': 'sorting_criteria',
         'options': [
             'Size',
             'PValue',
             'NumberOfRows'
         ]},
        {'name': 'normalization',
         'options': [
             'Column',
             'Row',
             'Overall',
             'None'
         ]},
        {'name': 'discretization',
         'options': [
             'NormalDist',
             'SimpleRange',
             'None'
         ]},
        {'name': 'symmetries',
         'options': [
             'Yes',
             'None'
         ]},
        {'name': 'missings_handler',
         'options': [
             'RemoveValue',
             'Replace'
         ]},
    ]
}


def parameters_to_iluapp_layout(parameters):
    res = []
    for param in parameters:
        name = param['name']
        if 'options' in param:
            button_type = gui_utils.Button.unidrop
            value = param['options']
        else:
            button_type = gui_utils.Button.input
            value = param['default']
        res.append((name, value, button_type))
    return res


def hash_params(params):
    return hashlib.sha256(str(params).encode('utf-8')).hexdigest()


def parse_bics_from_file(file_path):
    f = open(file_path, 'r')
    contents = f.read()

    bics = []

    # Regex to process biclusters
    matches = re.findall(
        r'I=(\[.+\]) \(\d+,\d+\) Y=(\[.*\]) X=(\[[\d,]*\]) pvalue=([\d.E-]+) area=([\d.E-]+)\n(([-\d:.]+[\s]{0,1})*)\n(([-\d:.]+[\s]{0,3})*)',
        contents)
    for items, cols, x, pvalue, area, real_matrix, _, matrix, _ in matches:
        cols = parse_string_list(cols)
        real_matrix = parse_matrix(real_matrix)
        matrix = parse_matrix(matrix)
        bics.append({'cols': cols, 'real_matrix': real_matrix, 'matrix': matrix, 'pvalue': pvalue, 'area': area})
    return bics


class BicPamsPyWrapper:
    def __init__(self):
        parameters = []
        for key in bicpams_parameters:
            parameters += bicpams_parameters[key]
        self.parameters = parameters

    def run(self, input_file, params):
        args = ['java', '-cp', '"bicpams.jar:lib/*"', 'tests.others.BicFranciscoTests']
        for param in self.parameters:
            name = param['name']
            value = params[name]
            args += ['--{}'.format(name), '{}'.format(value)]
        args += ['--file_path', input_file]

        command = ' '.join(args)
        print('Running {}'.format(command))
        subprocess.call(command, cwd=JAR_DIRECTORY, shell=True)
        output_file = '{}.bics'.format(input_file.split('.arff')[0])

        return parse_bics_from_file(output_file)
