import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Proxy.java
 * ----------
 * Stages 2-5 and the bonus. The only file that knows more than one backend
 * exists; every KvServer.java stays completely dumb.
 *
 *   --backends host:port                 -> Stage 2 (one backend,
 *                                            transparent pass-through,
 *                                            fast-fail on death)
 *   --backends h1:p1,h2:p2,h3:p3          -> Stage 3 (broadcast writes,
 *                                            round-robin reads, need >=2 up
 *                                            to accept a write)
 *   (automatic, on whenever 2+ backends)  -> Stage 4 (a backend that comes
 *                                            back up is caught up from the
 *                                            longest-running survivor before
 *                                            it rejoins the read rotation)
 *   --majority-read                       -> Stage 5 (GET votes across every
 *                                            ready backend, repairs the
 *                                            minority)
 *   --quorum-write                        -> Bonus (a write is acknowledged
 *                                            once a majority of the backends
 *                                            it was sent to confirm)
 *   --no-catchup                          -> disables Stage 4
 *
 * Run: java Proxy --port 7000 --backends 127.0.0.1:7101,127.0.0.1:7102,127.0.0.1:7103
 */
public class Proxy {
    private final List<Backend> backends;
    private final double opTimeout;
    private final double healthInterval;
    private final double healthTimeout;
    private final boolean majorityRead;
    private final boolean quorumWrite;
    private final boolean catchup;

    private final AtomicInteger rrIndex = new AtomicInteger(0);

    public Proxy(List<Backend> backends, double opTimeout, double healthInterval,
                 double healthTimeout, boolean majorityRead, boolean quorumWrite, boolean catchup) {
        this.backends = backends;
        this.opTimeout = opTimeout;
        this.healthInterval = healthInterval;
        this.healthTimeout = healthTimeout;
        this.majorityRead = majorityRead;
        this.quorumWrite = quorumWrite;
        this.catchup = catchup;
    }

    // ---------------------------------------------------------- helpers --
    private List<Backend> upBackends() {
        List<Backend> out = new ArrayList<>();
        for (Backend b : backends) if (b.up) out.add(b);
        return out;
    }

    private List<Backend> readyBackends() {
        List<Backend> out = new ArrayList<>();
        for (Backend b : backends) if (b.readReady) out.add(b);
        return out;
    }

    private Backend rrPick(List<Backend> candidates) {
        int idx = Math.floorMod(rrIndex.getAndIncrement(), candidates.size());
        return candidates.get(idx);
    }

    private void log(String msg) {
        System.out.println("[proxy] " + msg);
    }

    // -------------------------------------------------------- write path --
    private String doWrite(String verb, String key, String value) {
        boolean multi = backends.size() >= 2;
        List<Backend> up = upBackends();
        List<Backend> targets;
        if (multi) {
            if (up.size() < 2) return "ERR write_unavailable";
            targets = up;
        } else {
            if (up.isEmpty()) return "ERR backend_unavailable";
            targets = up;
        }

        String line = (value != null) ? verb + " " + key + " " + value : verb + " " + key;
        int needed = quorumWrite ? (targets.size() / 2 + 1) : targets.size();
        CountDownLatch latch = new CountDownLatch(needed);
        AtomicInteger okCount = new AtomicInteger(0);
        List<Thread> threads = new ArrayList<>();

        for (Backend b : targets) {
            Thread t = new Thread(() -> {
                String reply = b.call(line, opTimeout);
                if (reply == null) {
                    b.up = false;
                    b.readReady = false;
                    log("backend " + b.name + " appears DOWN");
                } else {
                    okCount.incrementAndGet();
                    latch.countDown();
                }
            });
            t.setDaemon(true);
            threads.add(t);
            t.start();
        }

        awaitLatch(latch, opTimeout + 0.5);

        if (quorumWrite && targets.size() >= 2) {
            if (okCount.get() >= needed) return "OK";
            joinAll(threads, opTimeout + 0.5);
            return okCount.get() >= needed ? "OK" : "ERR write_unavailable";
        } else {
            joinAll(threads, opTimeout + 0.5);
            if (multi) return okCount.get() >= 2 ? "OK" : "ERR write_unavailable";
            return okCount.get() >= 1 ? "OK" : "ERR backend_unavailable";
        }
    }

    private static void awaitLatch(CountDownLatch latch, double timeoutSeconds) {
        try {
            latch.await((long) (timeoutSeconds * 1000), TimeUnit.MILLISECONDS);
        } catch (InterruptedException ignored) {
        }
    }

    private static void joinAll(List<Thread> threads, double timeoutSeconds) {
        long ms = (long) (timeoutSeconds * 1000);
        for (Thread t : threads) {
            try {
                t.join(ms);
            } catch (InterruptedException ignored) {
            }
        }
    }

    // --------------------------------------------------------- read path --
    private String doRead(String key) {
        return majorityRead ? doReadMajority(key) : doReadRoundRobin(key);
    }

    private String doReadRoundRobin(String key) {
        List<String> tried = new ArrayList<>();
        for (int attempt = 0; attempt < 2; attempt++) {
            List<Backend> candidates = new ArrayList<>();
            for (Backend b : readyBackends()) if (!tried.contains(b.name)) candidates.add(b);
            if (candidates.isEmpty()) break;
            Backend b = rrPick(candidates);
            tried.add(b.name);
            String reply = b.call("GET " + key, opTimeout);
            if (reply == null) {
                b.up = false;
                b.readReady = false;
                log("backend " + b.name + " appears DOWN");
                continue;
            }
            return reply;
        }
        return "ERR backend_unavailable";
    }

    private String doReadMajority(String key) {
        List<Backend> candidates = readyBackends();
        if (candidates.isEmpty()) return "ERR backend_unavailable";

        Map<String, String> results = new ConcurrentHashMap<>();
        List<Thread> threads = new ArrayList<>();
        for (Backend b : candidates) {
            Thread t = new Thread(() -> {
                String reply = b.call("GET " + key, opTimeout);
                if (reply == null) {
                    b.up = false;
                    b.readReady = false;
                    log("backend " + b.name + " appears DOWN");
                } else {
                    results.put(b.name, reply);
                }
            });
            t.setDaemon(true);
            threads.add(t);
            t.start();
        }
        joinAll(threads, opTimeout + 0.5);

        if (results.isEmpty()) return "ERR backend_unavailable";

        Map<String, List<String>> counts = new LinkedHashMap<>();
        for (Map.Entry<String, String> e : results.entrySet()) {
            counts.computeIfAbsent(e.getValue(), k -> new ArrayList<>()).add(e.getKey());
        }

        int total = results.size();
        int majorityNeeded = total / 2 + 1;
        String winner = null;
        for (Map.Entry<String, List<String>> e : counts.entrySet()) {
            if (e.getValue().size() >= majorityNeeded) {
                winner = e.getKey();
                break;
            }
        }
        if (winner == null) return "ERR no_majority";

        for (Map.Entry<String, String> e : results.entrySet()) {
            if (!e.getValue().equals(winner)) {
                Backend backend = findByName(candidates, e.getKey());
                if (winner.startsWith("VALUE ")) {
                    String value = winner.substring("VALUE ".length());
                    backend.call("SET " + key + " " + value, opTimeout);
                } else if (winner.equals("NOT_FOUND")) {
                    backend.call("DEL " + key, opTimeout);
                }
                log("repaired " + e.getKey() + " for key '" + key + "' (had '" + e.getValue()
                        + "', majority said '" + winner + "')");
            }
        }
        return winner;
    }

    private static Backend findByName(List<Backend> list, String name) {
        for (Backend b : list) if (b.name.equals(name)) return b;
        return null;
    }

    // --------------------------------------------------------- dispatch --
    private String info() {
        String mode = majorityRead ? "majority" : "roundrobin";
        return String.format("INFO backends=%d up=%d read_ready=%d read_mode=%s",
                backends.size(), upBackends().size(), readyBackends().size(), mode);
    }

    String dispatch(String line) {
        if (line == null || line.isBlank()) return "ERR bad_command";
        String[] parts = line.split(" ", 3);
        String verb = parts[0].toUpperCase();

        if (verb.equals("SET") && parts.length == 3) return doWrite("SET", parts[1], parts[2]);
        if (verb.equals("DEL") && parts.length == 2) return doWrite("DEL", parts[1], null);
        if (verb.equals("GET") && parts.length == 2) return doRead(parts[1]);
        if (verb.equals("INFO") && parts.length == 1) return info();
        if (verb.equals("PING") && parts.length == 1) {
            List<Backend> up = upBackends();
            if (up.isEmpty()) return "ERR backend_unavailable";
            Backend b = rrPick(up);
            String reply = b.call("PING", opTimeout);
            return reply != null ? reply : "ERR backend_unavailable";
        }
        return "ERR bad_command";
    }

    // --------------------------------------------------- background loops --
    private void catchUp(Backend backend) {
        backend.catchingUp = true;
        try {
            List<Backend> sources = new ArrayList<>();
            for (Backend b : backends) if (b != backend && b.readReady) sources.add(b);
            if (sources.isEmpty()) {
                backend.readReady = true;
                log(backend.name + " back in the read rotation");
                return;
            }

            Backend bestSource = null;
            double bestUptime = -1;
            for (Backend s : sources) {
                String reply = s.call("INFO", opTimeout);
                if (reply != null && reply.startsWith("INFO ")) {
                    String[] p = reply.split(" ");
                    double uptime = Double.parseDouble(p[1]);
                    if (bestSource == null || uptime > bestUptime
                            || (uptime == bestUptime && s.name.compareTo(bestSource.name) < 0)) {
                        bestSource = s;
                        bestUptime = uptime;
                    }
                }
            }
            if (bestSource == null) {
                backend.readReady = true;
                log(backend.name + " back in the read rotation");
                return;
            }

            log("catching " + backend.name + " up from " + bestSource.name
                    + String.format(" (uptime %.2fs)", bestUptime));

            String dumpReply = bestSource.call("DUMP", opTimeout);
            if (dumpReply == null || !dumpReply.startsWith("DUMP ")) {
                log("catch-up for " + backend.name + " failed: source DUMP unreachable");
                return;
            }
            Map<String, String> snapshot = Json.decode(dumpReply.substring("DUMP ".length()));

            int loaded = 0;
            for (Map.Entry<String, String> e : snapshot.entrySet()) {
                String reply = backend.call("LOAD " + e.getKey() + " " + e.getValue(), opTimeout);
                if ("LOADED".equals(reply)) loaded++;
            }

            String heldReply = backend.call("DUMP", opTimeout);
            int heldCount = 0;
            if (heldReply != null && heldReply.startsWith("DUMP ")) {
                heldCount = Json.decode(heldReply.substring("DUMP ".length())).size();
            }

            log(String.format("%s catch-up done: %d/%d snapshot keys applied, %d keys now held "
                            + "(source had %d at snapshot time)",
                    backend.name, loaded, snapshot.size(), heldCount, snapshot.size()));
            backend.readReady = true;
            log(backend.name + " back in the read rotation");
        } finally {
            backend.catchingUp = false;
        }
    }

    private void healthCheckLoop() {
        while (true) {
            for (Backend b : backends) {
                String reply = b.call("PING", healthTimeout);
                if ("PONG".equals(reply)) {
                    boolean wasUp = b.up;
                    b.up = true;
                    if (!b.everChecked) {
                        // cold start: nothing to catch up from yet
                        b.readReady = true;
                        b.everChecked = true;
                    } else if (!wasUp) {
                        log("backend " + b.name + " is back up");
                        if (catchup && backends.size() >= 2 && !b.catchingUp) {
                            Thread t = new Thread(() -> catchUp(b));
                            t.setDaemon(true);
                            t.start();
                        } else {
                            b.readReady = true;
                        }
                    }
                } else {
                    if (b.up) log("backend " + b.name + " appears DOWN");
                    b.up = false;
                    b.readReady = false;
                    b.everChecked = true;
                }
            }
            try {
                Thread.sleep((long) (healthInterval * 1000));
            } catch (InterruptedException ignored) {
            }
        }
    }

    // ---------------------------------------------------------- serving --
    private void handleConn(Socket socket) {
        try (socket) {
            LineConn conn = new LineConn(socket);
            while (true) {
                String line;
                try {
                    line = conn.readLine();
                } catch (ConnectionClosedException e) {
                    break;
                }
                conn.sendLine(dispatch(line));
            }
        } catch (IOException ignored) {
        }
    }

    public void serve(String host, int port) throws IOException {
        Thread health = new Thread(this::healthCheckLoop);
        health.setDaemon(true);
        health.start();

        List<String> addrs = new ArrayList<>();
        for (Backend b : backends) addrs.add(b.address());

        try (ServerSocket listener = new ServerSocket()) {
            listener.setReuseAddress(true);
            listener.bind(new InetSocketAddress(host, port));
            System.out.println("[proxy] listening on " + host + ":" + port + ", backends=" + addrs);
            while (true) {
                Socket sock = listener.accept();
                Thread t = new Thread(() -> handleConn(sock));
                t.setDaemon(true);
                t.start();
            }
        }
    }

    private static List<Backend> parseBackends(String spec) {
        List<Backend> out = new ArrayList<>();
        String[] items = spec.split(",");
        for (int i = 0; i < items.length; i++) {
            String[] hp = items[i].trim().split(":");
            out.add(new Backend(hp[0], Integer.parseInt(hp[1]), "kv-" + (i + 1)));
        }
        return out;
    }

    public static void main(String[] args) throws IOException {
        String host = "127.0.0.1";
        int port = 7000;
        String backendsSpec = null;
        double opTimeout = 1.0;
        double healthInterval = 1.0;
        double healthTimeout = 0.5;
        boolean majorityRead = false;
        boolean quorumWrite = false;
        boolean noCatchup = false;

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--host" -> host = args[++i];
                case "--port" -> port = Integer.parseInt(args[++i]);
                case "--backends" -> backendsSpec = args[++i];
                case "--op-timeout" -> opTimeout = Double.parseDouble(args[++i]);
                case "--health-interval" -> healthInterval = Double.parseDouble(args[++i]);
                case "--health-timeout" -> healthTimeout = Double.parseDouble(args[++i]);
                case "--majority-read" -> majorityRead = true;
                case "--quorum-write" -> quorumWrite = true;
                case "--no-catchup" -> noCatchup = true;
                default -> throw new IllegalArgumentException("unknown flag: " + args[i]);
            }
        }
        if (backendsSpec == null) {
            System.err.println("usage: java Proxy --backends host:port[,host:port...] [--port 7000] ...");
            System.exit(2);
        }

        List<Backend> backends = parseBackends(backendsSpec);
        Proxy proxy = new Proxy(backends, opTimeout, healthInterval, healthTimeout,
                majorityRead, quorumWrite, !noCatchup);
        proxy.serve(host, port);
    }
}
