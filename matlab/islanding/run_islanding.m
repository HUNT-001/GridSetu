function S = run_islanding(use_simulink)
%RUN_ISLANDING Simulate the critical bus through a feeder trip, with and without GridSetu.
%   S = run_islanding()       uses Simulink when it is installed, otherwise the plain loop
%   S = run_islanding(false)  plain MATLAB/Octave loop only
%
%   Builds gridsetu_islanding.slx if needed, runs GridSetu and the baseline, checks Simulink
%   against ISLANDING_REFERENCE, writes results/islanding_summary.json and
%   results/islanding_waveforms.png, and prints the key numbers.

here = fileparts(mfilename('fullpath'));
addpath(here);
out_dir = fullfile(here, 'results');
if ~exist(out_dir, 'dir'), mkdir(out_dir); end
is_octave = exist('OCTAVE_VERSION', 'builtin') > 0;
if nargin < 1
    use_simulink = ~is_octave && ~isempty(ver('simulink'));
end
p = islanding_params();

fprintf('Reference loop (plain MATLAB) ... ');
[G, xg] = islanding_reference(1, p);
[Bl, xb] = islanding_reference(0, p);
fprintf('done\n');

S = struct();
S.engine = 'reference loop';
if use_simulink
    mdl = 'gridsetu_islanding';
    if ~exist(fullfile(here, [mdl '.slx']), 'file'), build_islanding_model(); end
    load_system(fullfile(here, [mdl '.slx']));
    blk = [mdl '/Variant (1 = GridSetu, 0 = baseline)'];
    Ys = cell(1, 2);
    vals = [1 0];
    for k = 1:2
        set_param(blk, 'Value', num2str(vals(k)));
        fprintf('Simulink, variant %d ... ', vals(k));
        so = sim(mdl);
        Ys{k} = as_rows(so.get('y_isl'));
        fprintf('done (%d samples)\n', size(Ys{k}, 1));
    end
    set_param(blk, 'Value', '1');
    d = max(max_diff(Ys{1}, G), max_diff(Ys{2}, Bl));
    fprintf('Simulink vs reference loop: largest difference %.2e\n', d);
    S.engine = 'Simulink';
    S.simulink_vs_reference_max_abs_diff = d;
    G = Ys{1}; Bl = Ys{2};
end

% ---- key numbers -----------------------------------------------------------------------
t = G(:, 1); f = G(:, 2); V = G(:, 3);
isl = t >= p.t_trip & t < p.t_return;
after = t >= p.t_trip + 0.2;
i_close = find(G(:, 10) > 0.5 & t > p.t_return, 1);
S.event_timeline_s = struct('feeder_trips', p.t_trip, 'pump_starts', p.t_pump, ...
    'grid_returns', p.t_return);
S.gridsetu.critical_bus_below_0_9pu_ms = round(1e3*sum(V < 0.9)*p.dt*p.log_every);
S.gridsetu.island_formed_after_ms = round(1e3*(t(find(G(:, 11) > 0.5, 1)) - p.t_trip));
S.gridsetu.min_voltage_pu_during_transfer = rnd(min(V(isl)), 3);
S.gridsetu.min_voltage_pu_after_transfer = rnd(min(V(after & t < p.t_end)), 3);
S.gridsetu.min_frequency_hz = rnd(min(f(after & isl)), 3);
S.gridsetu.max_frequency_hz = rnd(max(f(after)), 3);
if isempty(i_close)
    S.gridsetu.reconnected_at_s = NaN;
else
    S.gridsetu.reconnected_at_s = rnd(t(i_close), 3);
end
S.gridsetu.peak_inverter_kva = rnd(max(hypot(G(:, 4), G(:, 5))), 1);
S.gridsetu.peak_battery_current_a = rnd(max(G(:, 7)), 1);
S.gridsetu.critical_energy_served_kwh = rnd(xg(13), 4);
S.gridsetu.critical_energy_not_served_kwh = rnd(xg(14), 4);
S.baseline.critical_bus_dark_s = rnd(sum(Bl(:, 3) < 0.5)*p.dt*p.log_every, 3);
S.baseline.critical_energy_not_served_kwh = rnd(xb(14), 4);
S.note = ['SIMULATION, average-value model with assumed inverter settings. The outage is ' ...
    'compressed to 4 s; in the stress week outages last up to an hour and the battery holds ' ...
    '2 hours of Tier-1 energy for them.'];

fid = fopen(fullfile(out_dir, 'islanding_summary.json'), 'w');
fprintf(fid, '%s', jsonencode(S));
fclose(fid);

fprintf('\nFeeder trips at %.1f s. GridSetu forms the island after %d ms; the clinic sees under 0.9 pu for %d ms.\n', ...
    p.t_trip, S.gridsetu.island_formed_after_ms, S.gridsetu.critical_bus_below_0_9pu_ms);
fprintf('In the island: frequency %.2f to %.2f Hz, voltage never below %.3f pu (pump start included).\n', ...
    S.gridsetu.min_frequency_hz, S.gridsetu.max_frequency_hz, S.gridsetu.min_voltage_pu_after_transfer);
fprintf('Grid back at %.1f s, out of phase; tie closed in phase at %.2f s.\n', p.t_return, S.gridsetu.reconnected_at_s);
fprintf('Baseline: critical bus dark for %.1f s (the whole outage).\n', S.baseline.critical_bus_dark_s);

plot_waveforms(G, Bl, p, fullfile(out_dir, 'islanding_waveforms.png'));
fprintf('Results written to %s\n', out_dir);
end

% ------------------------------------------------------------------------------------------
function y = rnd(x, n)
% round to n decimals (two-argument round is not in Octave)
y = round(x*10^n)/10^n;
end

function Y = as_rows(Y)
% To Workspace may return N x 12 or 12 x 1 x N depending on the signal's dimensions.
if ndims(Y) == 3
    Y = permute(reshape(Y, size(Y, 1)*size(Y, 2), size(Y, 3)), [2 1]);
end
end

function d = max_diff(A, B)
n = min(size(A, 1), size(B, 1));
A = A(1:n, :); B = B(1:n, :);
both_nan = isnan(A) & isnan(B);
D = abs(A - B);
D(both_nan) = 0;
D(isnan(D)) = Inf;
d = max(D(:));
if size(A, 1) ~= size(B, 1), d = max(d, Inf); end
end

function plot_waveforms(G, Bl, p, file)
navy = [0.05 0.13 0.25]; teal = [0.07 0.47 0.45]; grey = [0.62 0.64 0.68]; amber = [0.96 0.65 0.14];
t = G(:, 1);
fig = figure('Color', 'w', 'Position', [60 60 1400 900]);
ev = [p.t_trip p.t_pump p.t_return];
evl = {'feeder trips', 'pump starts', 'grid returns'};

subplot(3, 2, 1);
plot(t, Bl(:, 3), 'Color', grey, 'LineWidth', 1.6); hold on;
plot(t, G(:, 3), 'Color', navy, 'LineWidth', 1.6);
mark(ev, evl, [-0.05 1.1]); ylim([-0.05 1.1]); xlim([0 p.t_end]); grid on;
ylabel('Voltage (pu)'); title('Critical-bus voltage: clinic, school, pump, street lights');
legend({'Baseline: dark until the grid returns', 'GridSetu: islanded on the battery'}, 'Location', 'southeast');

subplot(3, 2, 2);
w = t >= p.t_trip - 0.05 & t <= p.t_trip + 0.25;
plot(1e3*(t(w) - p.t_trip), Bl(w, 3), 'Color', grey, 'LineWidth', 1.6); hold on;
plot(1e3*(t(w) - p.t_trip), G(w, 3), 'Color', navy, 'LineWidth', 1.6);
plot([-50 250], [0.9 0.9], '--', 'Color', amber);
ylim([-0.05 1.1]); grid on; xlabel('Milliseconds after the feeder trips'); ylabel('Voltage (pu)');
title('Zoom: detect (40 ms), open the tie (60 ms), form the island');

subplot(3, 2, 3);
plot(t, G(:, 2), 'Color', navy, 'LineWidth', 1.6); hold on;
mark(ev, evl, [49.6 50.4]); ylim([49.6 50.4]); xlim([0 p.t_end]); grid on;
text(p.t_return + 0.1, 50.36, 'deliberate +0.3 Hz to catch the grid''s phase', 'FontSize', 8, 'Color', [0.3 0.3 0.3]);
ylabel('Frequency (Hz)'); title('Frequency set by the battery inverter in the island');

subplot(3, 2, 4);
plot(t, G(:, 4), 'Color', navy, 'LineWidth', 1.6); hold on;
plot(t, G(:, 6), 'Color', teal, 'LineWidth', 1.6);
plot(t, Bl(:, 6), 'Color', grey, 'LineWidth', 1.2);
mark(ev, evl, [0 100]); xlim([0 p.t_end]); grid on; ylabel('kW');
title('Power: inverter output and critical load served');
legend({'Inverter output', 'Critical load served, GridSetu', 'Critical load served, baseline'}, 'Location', 'northeast');

subplot(3, 2, 5);
plot(t, G(:, 7), 'Color', navy, 'LineWidth', 1.6); hold on;
mark(ev, evl, [0 140]); xlim([0 p.t_end]); grid on; ylabel('Battery current (A)'); xlabel('Time (s)');
title(sprintf('Battery pack: %.0f V nominal, state of charge %.0f%%', p.cells*3.2, 100*p.soc0));

subplot(3, 2, 6);
a = G(:, 12); a(t < p.t_return | G(:, 10) > 0.5) = NaN;
plot(t, a, 'Color', navy, 'LineWidth', 1.6); hold on;
plot([p.t_return p.t_end], [10 10], '--', 'Color', amber);
plot([p.t_return p.t_end], [-10 -10], '--', 'Color', amber);
mark(ev, evl, [-180 180]); ylim([-180 180]); xlim([0 p.t_end]); grid on;
ylabel('Island angle to grid (deg)'); xlabel('Time (s)');
title('Resynchronising: close only within 10 deg and 0.1 Hz');

if exist('sgtitle', 'file')
    sgtitle('SIMULATION: average-value model, assumed inverter settings - GridSetu feeder F07 critical bus');
end
print(fig, file, '-dpng', '-r130');
end

function mark(ev, evl, yl)
for k = 1:numel(ev)
    plot([ev(k) ev(k)], yl, ':', 'Color', [0.4 0.4 0.4]);
    text(ev(k), yl(2), [' ' evl{k}], 'VerticalAlignment', 'top', 'FontSize', 8, 'Color', [0.3 0.3 0.3]);
end
end
