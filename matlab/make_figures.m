function make_figures(do_plot)
%MAKE_FIGURES Deck graphs 3-8 from the results of run_f07 (stress week).
%   make_figures          % writes PNGs to results/figures
%   make_figures(false)   % only checks the data (used in automated tests)
%   Uses base MATLAB plotting only.

if nargin < 1, do_plot = true; end
here = fileparts(mfilename('fullpath'));
res = fullfile(here, 'results');
figdir = fullfile(res, 'figures');
if do_plot && ~exist(figdir, 'dir'), mkdir(figdir); end
p = jsondecode(fileread(fullfile(here, 'f07_params.json')));
S = jsondecode(fileread(fullfile(res, 'summary.json')));
names = {'baseline', 'gridsetu', 'gridsetu_distributed'};
labels = {'Baseline', 'GridSetu (battery at transformer)', 'GridSetu (storage split across circuits)'};
cols = [0.61 0.64 0.69; 0.04 0.12 0.23; 0.06 0.46 0.43];
nbc = p.topology.buses_per_circuit;
nb = p.topology.circuits * nbc;
seg = p.topology.circuit_length_m / nbc;
lo = p.v_limit_pu(1);
tag = 'SIMULATION: synthetic data, not field measurement - MATLAB low-voltage model, assumed network';

D = cell(1, 3); TS = cell(1, 3);
for c = 1:3
    [TS{c}, D{c}] = read_steps(fullfile(res, sprintf('f07_stress_%s_steps.csv', names{c})), nb);
end
% column indices in the steps file (after the timestamp)
cV = 1; cBus = 3; cLine = 7; cCu = 8; cNl = 9; cPdt = 10; cOn = 13; cHot = 15; cImp = 17; cVb = 18:(17 + nb);

% worst evening step of the baseline
hh = cellfun(@(x) str2double(x(12:13)) + str2double(x(15:16)) / 60, TS{1});
ev = find(hh >= 17.5 & hh <= 19.25 & D{1}(:, cOn) == 1);
[~, k] = min(D{1}(ev, cV)); t_star = ev(k);
wb = D{1}(t_star, cBus);
circ = floor((wb - 1) / nbc);
abc = 'ABC';
cname = abc(circ + 1);
buses = circ * nbc + (1:nbc);
x = (1:nbc) * seg;
day = floor(((1:size(D{1}, 1))' - 1) / 96) + 1;
assert(numel(buses) == nbc && all(isfinite(D{1}(t_star, cVb(buses)))), 'make_figures: bad profile data');
if ~do_plot
    fprintf('make_figures: data OK (worst step %s, circuit %c)\n', TS{1}{t_star}, cname);
    return;
end

% 3 voltage along the worst circuit
f = figure('Color', 'w', 'Position', [100 100 1000 520]); hold on; box off; grid on;
for c = 1:3
    plot(x, D{c}(t_star, cVb(buses)), '-o', 'Color', cols(c, :), 'LineWidth', 2, ...
        'DisplayName', sprintf('%s: tail %.3f pu', labels{c}, D{c}(t_star, cVb(buses(end)))));
end
xlim([0 x(end) * 1.04]);
yline_(lo, 'lower limit');
xlabel(sprintf('Distance along circuit %c from the transformer (m)', cname));
ylabel('Voltage (pu of 415 V)');
title(sprintf('Voltage along circuit %c at %s, worst evening step', cname, TS{1}{t_star}(1:16)));
legend('Location', 'southwest'); note_(tag); save_(f, figdir, 'lv_voltage_profile');

% 4 voltage heat-strip, baseline vs storage split
f = figure('Color', 'w', 'Position', [100 100 1200 620]);
for j = 1:2
    c = [1 3]; c = c(j);
    subplot(2, 1, j);
    imagesc((0:size(D{c}, 1) - 1) / 96, 1:nb, D{c}(:, cVb)', [0.80 1.06]);
    colormap(flipud(hot)); colorbar; ylabel('Bus');
    title(sprintf('%s: violation bus-hours %.0f', labels{c}, S.(['stress_' names{c}]).voltage_violation_bus_hours));
end
xlabel('Day of the stress week'); note_(tag); save_(f, figdir, 'lv_voltage_heatstrip');

% 5 daily technical losses
f = figure('Color', 'w', 'Position', [100 100 1000 520]);
L = zeros(7, 3);
for c = 1:3
    loss = (D{c}(:, cLine) + D{c}(:, cCu) + D{c}(:, cNl)) * 0.25;
    L(:, c) = accumarray(day, loss, [7 1]);
end
b = bar(L, 'grouped'); for c = 1:3, b(c).FaceColor = cols(c, :); end
set(gca, 'XTickLabel', {'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'}); box off; grid on;
ylabel('Technical losses (kWh/day)'); title('Technical losses per day, stress week (lines + transformer)');
legend(cellfun(@(l, n) sprintf('%s: %.0f kWh/week', l, S.(['stress_' n]).technical_loss_kwh), labels, names, ...
    'UniformOutput', false), 'Location', 'southoutside');
note_(tag); save_(f, figdir, 'lv_losses_daily');

% 6 transformer hot-spot temperature
f = figure('Color', 'w', 'Position', [100 100 1100 480]); hold on; box off; grid on;
tt = (0:size(D{1}, 1) - 1) / 96;
for c = 1:2
    plot(tt, D{c}(:, cHot), 'Color', cols(c, :), 'LineWidth', 1.4, 'DisplayName', ...
        sprintf('%s: peak %.1f C', labels{c}, S.(['stress_' names{c}]).max_hotspot_c));
end
yline_(98, '98 C: normal ageing rate (IEC 60076-7)');
xlabel('Day of the stress week'); ylabel('Hot-spot temperature (C)');
title('Transformer hot-spot temperature, stress week'); legend('Location', 'southoutside');
note_(tag); save_(f, figdir, 'lv_hotspot');

% 7 what a one-point model misses
f = figure('Color', 'w', 'Position', [100 100 620 560]); hold on; box off; grid on;
on = D{1}(:, cOn) == 1;
scatter(D{1}(on, cImp), D{1}(on, cPdt), 10, cols(2, :), 'filled');
m = max([D{1}(on, cImp); D{1}(on, cPdt)]) * 1.05;
plot([0 m], [0 m], '--', 'Color', cols(1, :));
axis([0 m 0 m]);
xlabel('Feeder import, one-point Python model (kW)');
ylabel('Power into the transformer, MATLAB network model (kW)');
title({'The gap above the line is the technical loss', 'the one-point model cannot see'});
note_(tag); save_(f, figdir, 'lv_model_agreement');

% 8 placement comparison
f = figure('Color', 'w', 'Position', [100 100 1200 440]);
mets = {'technical_loss_kwh', 'voltage_violation_bus_hours', 'peak_transformer_loading_pu'};
ttl = {'Technical losses (kWh/week)', 'Voltage violations (bus-hours/week)', 'Peak transformer loading (pu)'};
for j = 1:3
    subplot(1, 3, j);
    v = cellfun(@(n) S.(['stress_' n]).(mets{j}), names);
    b = bar(v); b.FaceColor = 'flat'; b.CData = cols; box off; grid on;
    set(gca, 'XTickLabel', {'Baseline', 'At transformer', 'Split'}); title(ttl{j});
end
note_(tag); save_(f, figdir, 'lv_placement');
fprintf('Figures written to %s\n', figdir);
end

function [ts, A] = read_steps(file, nb)
fid = fopen(file, 'r'); fgetl(fid);
C = textscan(fid, ['%s' repmat(' %f', 1, 17 + nb)], 'Delimiter', ',');
fclose(fid);
ts = C{1}; A = cell2mat(C(2:end));
end

function yline_(y, txt)
xl = xlim; plot(xl, [y y], '--', 'Color', [0.96 0.65 0.14], 'HandleVisibility', 'off');
text(xl(1), y, ['  ' txt], 'VerticalAlignment', 'bottom', 'Color', [0.42 0.45 0.5], 'FontSize', 9);
end

function note_(txt)
annotation('textbox', [0 0 1 0.04], 'String', txt, 'EdgeColor', 'none', ...
    'HorizontalAlignment', 'right', 'FontSize', 8, 'Color', [0.42 0.45 0.5]);
end

function save_(f, d, name)
print(f, fullfile(d, [name '.png']), '-dpng', '-r200');
close(f);
end
