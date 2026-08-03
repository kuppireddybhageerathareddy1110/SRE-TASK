import java.io.IOException;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * KvServer.java
 * -------------
 * Stage 1. A dumb in-memory key-value map behind a TCP listener. Thread per
 * connection. Knows nothing about proxies, replication, or any other copy
 * of itself -- all of that intelligence lives in Proxy.java.
 *
 * Client-facing commands:
 *   SET key value  -> OK
 *   GET key        -> VALUE value | NOT_FOUND
 *   DEL key        -> OK | NOT_FOUND
 *   PING           -> PONG
 *   (anything else) -> ERR bad_command   (connection stays open)
 *
 * Admin commands (used by Proxy.java, and directly for Stage 4/5 testing):
 *   INFO             -> INFO <uptimeSeconds> <keyCount>
 *   DUMP             -> DUMP <json of the whole map>
 *   LOAD key value   -> LOADED | SKIPPED   (set-if-absent)
 *   CORRUPT key value -> OK                (same as SET; a separate verb
 *                        purely so Stage 5 tests can manufacture
 *                        disagreement deliberately)
 *
 * Run: java KvServer --port 7101 [--host 127.0.0.1]
 */
public class KvServer {

    /** The store itself: one map, guarded implicitly by using a
     * ConcurrentHashMap (equivalent in spirit to Python's dict + RLock). */
    static class Store {
        private final Map<String, String> data = new ConcurrentHashMap<>();
        private final long startNanos = System.nanoTime();

        String get(String key) {
            return data.get(key);
        }

        void set(String key, String value) {
            data.put(key, value);
        }

        boolean delete(String key) {
            return data.remove(key) != null;
        }

        /** Used by LOAD: set only if absent. Returns true iff it set the key. */
        boolean setIfAbsent(String key, String value) {
            return data.putIfAbsent(key, value) == null;
        }

        Map<String, String> dump() {
            return Map.copyOf(data);
        }

        int keyCount() {
            return data.size();
        }

        double uptimeSeconds() {
            return (System.nanoTime() - startNanos) / 1_000_000_000.0;
        }
    }

    private final Store store = new Store();

    /** Same dispatch logic as kvserver.py's KVServer.dispatch(). */
    String dispatch(String line) {
        if (line == null || line.isBlank()) return "ERR bad_command";
        String[] parts = line.split(" ", 3);
        String verb = parts[0].toUpperCase();

        if (verb.equals("SET") && parts.length == 3) {
            store.set(parts[1], parts[2]);
            return "OK";
        }
        if (verb.equals("GET") && parts.length == 2) {
            String v = store.get(parts[1]);
            return v != null ? "VALUE " + v : "NOT_FOUND";
        }
        if (verb.equals("DEL") && parts.length == 2) {
            return store.delete(parts[1]) ? "OK" : "NOT_FOUND";
        }
        if (verb.equals("PING") && parts.length == 1) {
            return "PONG";
        }
        if (verb.equals("INFO") && parts.length == 1) {
            return String.format("INFO %.3f %d", store.uptimeSeconds(), store.keyCount());
        }
        if (verb.equals("DUMP") && parts.length == 1) {
            return "DUMP " + Json.encode(store.dump());
        }
        if (verb.equals("LOAD") && parts.length == 3) {
            return store.setIfAbsent(parts[1], parts[2]) ? "LOADED" : "SKIPPED";
        }
        if (verb.equals("CORRUPT") && parts.length == 3) {
            store.set(parts[1], parts[2]);
            return "OK";
        }
        return "ERR bad_command";
    }

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
            // peer reset, etc. -- just drop the connection
        }
    }

    private void serve(String host, int port) throws IOException {
        try (ServerSocket listener = new ServerSocket()) {
            listener.setReuseAddress(true);
            listener.bind(new java.net.InetSocketAddress(host, port));
            System.out.println("[kvserver] listening on " + host + ":" + port);
            while (true) {
                Socket sock = listener.accept();
                Thread t = new Thread(() -> handleConn(sock));
                t.setDaemon(true);
                t.start();
            }
        }
    }

    public static void main(String[] args) throws IOException {
        String host = "127.0.0.1";
        int port = -1;
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--host" -> host = args[++i];
                case "--port" -> port = Integer.parseInt(args[++i]);
                default -> throw new IllegalArgumentException("unknown flag: " + args[i]);
            }
        }
        if (port == -1) {
            System.err.println("usage: java KvServer --port <port> [--host <host>]");
            System.exit(2);
        }
        new KvServer().serve(host, port);
    }
}
