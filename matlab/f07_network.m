function net = f07_network(p)
%F07_NETWORK Per-unit radial network of pilot feeder F07 from f07_params.json.
%   Node 1 is the transformer LV busbar (node 0 in the Python twin), fed from the
%   11 kV source through the transformer impedance. Nodes 2..22 are load buses 1..21.
%   net.parent(k) is the node that feeds node k (0 = the source).

base = p.base_kva;
vn = p.v_nominal_ll_v;
zbase = (vn / 1000)^2 / (base / 1000);                       % ohm

tr = p.transformer;
r_pct = tr.load_loss_w / (tr.rating_kva * 1000) * 100;
x_pct = sqrt(tr.impedance_pct^2 - r_pct^2);
scale = (tr.lv_open_circuit_v / vn)^2 * (base / tr.rating_kva);   % to 415 V and base kVA
z_dt = complex(r_pct, x_pct) / 100 * scale;

topo = p.topology;
ln = p.line;
seg_km = topo.circuit_length_m / topo.buses_per_circuit / 1000;
z_seg = complex(ln.r_ohm_per_km, ln.x_ohm_per_km) * seg_km / zbase;

nb = topo.circuits * topo.buses_per_circuit;
parent = zeros(nb + 1, 1);
for b = 1:nb
    k = mod(b - 1, topo.buses_per_circuit);
    if k == 0
        parent(b + 1) = 1;          % first bus of a circuit hangs off the LV busbar
    else
        parent(b + 1) = b;          % otherwise off the previous bus
    end
end
z = repmat(z_seg, nb + 1, 1);
z(1) = z_dt;

net.parent = parent;
net.z = z;
net.v_src = tr.lv_open_circuit_v / vn;
net.n_bus = nb;
net.base_kva = base;
net.zbase_ohm = zbase;
end
