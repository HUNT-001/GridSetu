function summary = run_f07(in_dir, out_dir)
%RUN_F07 Low-voltage study of pilot feeder F07: technical losses, voltage, transformer ageing.
%
%   run_f07                       % reads ../outputs/matlab, writes ./results
%
%   Inputs come from the Python simulator: `python -m gridsetu export-matlab`.
%   For each week (stress, representative) and scenario in f07_params.json it solves a
%   backward/forward-sweep load flow for every 15-minute step, runs the IEC 60076-7
%   transformer thermal model, and writes:
%     results/f07_<week>_<scenario>_steps.csv   per-step results incl. every bus voltage
%     results/summary.json                      one summary per case
%   It checks the energy balance against the Python simulator and, if the Python twin's
%   results exist (outputs/lv/), reports the largest difference between the two models.
%   Runs in MATLAB R2019b+ and GNU Octave 7+ (base functions only, no toolboxes).

here = fileparts(mfilename('fullpath'));
if nargin < 1 || isempty(in_dir),  in_dir = fullfile(here, '..', 'outputs', 'matlab'); end
if nargin < 2 || isempty(out_dir), out_dir = fullfile(here, 'results'); end
if ~exist(out_dir, 'dir'), mkdir(out_dir); end

p = jsondecode(fileread(fullfile(here, 'f07_params.json')));
net = f07_network(p);
base = net.base_kva;
nb = net.n_bus;
tanphi = tan(acos(p.load_power_factor));
vlo = p.v_limit_pu(1); vhi = p.v_limit_pu(2);
weeks = {'stress', 'representative'};
scen = fieldnames(p.scenarios);
summary = struct();

for w = 1:numel(weeks)
    for c = 1:numel(scen)
        sc = p.scenarios.(scen{c});
        [ts, P] = read_loads(fullfile(in_dir, sprintf('f07_loads_%s_%s.csv', weeks{w}, sc.variant)), nb);
        F = read_feeder(fullfile(in_dir, sprintf('f07_feeder_%s_%s.csv', weeks{w}, sc.variant)));
        T = size(P, 1);
        inj = F.battery_kw + F.community_pv_kw;
        on = F.energized == 1;
        sb = sc.storage_buses(:)';

        % energy balance: bus loads minus storage injection = Python's feeder import
        bal = max(abs(sum(P(on, :), 2) - inj(on) - F.import_kw(on)));
        if bal > 1e-2
            error('run_f07:balance', 'Energy balance off by %.4f kW (%s/%s)', bal, weeks{w}, scen{c});
        end

        R = nan(T, 13); V = nan(T, nb);
        % columns: v_min v_max v_min_bus n_under n_over load line_loss dt_cu dt_nl p_dt K iters energized
        for t = 1:T
            if ~on(t)
                R(t, :) = [NaN NaN NaN 0 0 0 0 0 0 0 0 NaN 0];
                continue;
            end
            s = zeros(nb + 1, 1);
            s(2:end) = (P(t, :)' + 1i * tanphi * max(P(t, :)', 0)) / base;
            for b = sb
                s(b + 1) = s(b + 1) - inj(t) / numel(sb) / base;
            end
            [v, ibr, it] = bfs_loadflow(net, s, p.solver.tol_pu, p.solver.max_iter);
            vm = abs(v(2:end));
            [vmin, imin] = min(vm);
            line_loss = sum(abs(ibr(2:end)).^2 .* real(net.z(2:end))) * base;
            dt_cu = abs(ibr(1))^2 * real(net.z(1)) * base;
            dt_nl = p.transformer.no_load_loss_w / 1000;
            s_src = net.v_src * conj(ibr(1));
            R(t, :) = [vmin, max(vm), imin, sum(vm < vlo), sum(vm > vhi), sum(P(t, :)), line_loss, ...
                       dt_cu, dt_nl, real(s_src) * base + dt_nl, abs(s_src) * base / p.transformer.rating_kva, it, 1];
            V(t, :) = vm';
        end
        K = R(:, 11);
        [th_o, th_h, age] = dt_thermal(K, F.ambient_c, on, p);

        name = sprintf('%s_%s', weeks{w}, scen{c});
        write_steps(fullfile(out_dir, sprintf('f07_%s_steps.csv', name)), ts, R, th_o, th_h, age, F.import_kw, V);
        summary.(name) = summarise(R, th_h, age, ts);
        fprintf('%-34s losses %7.1f kWh (%5.2f %%)  violations %6.1f bus-h  min V %.3f pu  peak K %.3f  ageing %.3f h\n', ...
            name, summary.(name).technical_loss_kwh, summary.(name).technical_loss_pct, ...
            summary.(name).voltage_violation_bus_hours, summary.(name).min_voltage_pu, ...
            summary.(name).peak_transformer_loading_pu, summary.(name).ageing_equivalent_hours);
    end
end

fid = fopen(fullfile(out_dir, 'summary.json'), 'w');
fprintf(fid, '%s\n', jsonencode(summary));
fclose(fid);
compare_with_python(out_dir, fullfile(here, '..', 'outputs', 'lv'), weeks, scen);
fprintf('Results written to %s\n', out_dir);
end

% -------------------------------------------------------------------------------------
function [ts, P] = read_loads(file, nb)
fid = fopen(file, 'r');
fgetl(fid);                                          % header
C = textscan(fid, ['%s' repmat(' %f', 1, nb)], 'Delimiter', ',');
fclose(fid);
ts = C{1};
P = cell2mat(C(2:end));
end

function F = read_feeder(file)
fid = fopen(file, 'r');
fgetl(fid);
C = textscan(fid, '%s %f %f %f %f %f %f %s', 'Delimiter', ',');
fclose(fid);
F.import_kw = C{2}; F.battery_kw = C{3}; F.community_pv_kw = C{4};
F.energized = C{5}; F.tier1_islanded_kw = C{6}; F.ambient_c = C{7};
end

function s = summarise(R, th_h, age, ts)
h = 0.25;
on = R(:, 13) == 1;
line = sum(R(:, 7)) * h;
dt = sum(R(:, 8) + R(:, 9)) * h;
p_dt = R(:, 10); p_dt(~on) = 0;
e_in = sum(max(p_dt, 0)) * h;
viol = R(:, 4) + R(:, 5);
hh = cellfun(@(x) str2double(x(12:13)) + str2double(x(15:16)) / 60, ts);
ev = hh >= 17.5 & hh <= 19.25;
s.energized_hours = sum(on) * h;
s.energy_from_transformer_kwh = round2(e_in, 2);
s.line_loss_kwh = round2(line, 2);
s.transformer_loss_kwh = round2(dt, 2);
s.technical_loss_kwh = round2(line + dt, 2);
s.technical_loss_pct = round2(100 * (line + dt) / e_in, 3);
s.voltage_violation_bus_hours = round2(sum(viol) * h, 2);
s.steps_with_violation_pct = round2(100 * mean(viol(on) > 0), 2);
s.min_voltage_pu = round2(min(R(:, 1)), 4);
s.evening_min_voltage_pu_mean = round2(mean(R(ev, 1), 'omitnan'), 4);
s.peak_transformer_loading_pu = round2(max(R(:, 11)), 4);
s.max_hotspot_c = round2(max(th_h), 2);
s.ageing_equivalent_hours = round2(sum(age * h), 3);
s.elapsed_hours = numel(on) * h;
end

function y = round2(x, d)
y = round(x * 10^d) / 10^d;
end

function write_steps(file, ts, R, th_o, th_h, age, imp, V)
fid = fopen(file, 'w');
fprintf(fid, 'timestamp,v_min_pu,v_max_pu,v_min_bus,n_bus_under,n_bus_over,load_kw,line_loss_kw,dt_cu_loss_kw,dt_nl_loss_kw,p_dt_kw,K,iters,energized,theta_oil_c,theta_hotspot_c,ageing_rate,python_import_kw');
fprintf(fid, ',v_bus_%02d', 1:size(V, 2));
fprintf(fid, '\n');
for t = 1:numel(ts)
    fprintf(fid, '%s', ts{t});
    fprintf(fid, ',%.10g', [R(t, :), th_o(t), th_h(t), age(t), imp(t), V(t, :)]);
    fprintf(fid, '\n');
end
fclose(fid);
end

function compare_with_python(mdir, pdir, weeks, scen)
if ~exist(fullfile(pdir, 'summary.json'), 'file')
    fprintf('Python twin results not found in %s (run: python -m gridsetu lv-study)\n', pdir);
    return;
end
worst = 0; what = '';
for w = 1:numel(weeks)
    for c = 1:numel(scen)
        f = sprintf('f07_%s_%s_steps.csv', weeks{w}, scen{c});
        a = dlmread(fullfile(mdir, f), ',', 1, 1);
        b = dlmread(fullfile(pdir, f), ',', 1, 1);
        cols = [1 7 8 11 15];            % v_min, line loss, dt copper loss, K, hot-spot
        d = abs(a(:, cols) - b(:, cols));
        d(isnan(d)) = 0;
        if max(d(:)) > worst, worst = max(d(:)); what = f; end
    end
end
fprintf('MATLAB vs Python twin: largest difference %.2e (in %s)\n', worst, what);
end
