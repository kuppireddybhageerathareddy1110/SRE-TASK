import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.Socket;

/**
 * Client.java
 * -----------
 * Minimal CLI client, mirroring client.py. Two modes:
 *
 *   Interactive:
 *       java Client --host 127.0.0.1 --port 9000
 *       > SET foo bar
 *       OK
 *       > GET foo
 *       VALUE bar
 *
 *   One-shot:
 *       java Client --host 127.0.0.1 --port 9000 --cmd "GET foo"
 */
public class Client {
    public static void main(String[] args) throws IOException {
        String host = "127.0.0.1";
        int port = -1;
        String oneShot = null;

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--host" -> host = args[++i];
                case "--port" -> port = Integer.parseInt(args[++i]);
                case "--cmd" -> oneShot = args[++i];
                default -> throw new IllegalArgumentException("unknown flag: " + args[i]);
            }
        }
        if (port == -1) {
            System.err.println("usage: java Client --port <port> [--host <host>] [--cmd \"GET foo\"]");
            System.exit(2);
        }

        Socket sock = new Socket(host, port);
        LineConn conn = new LineConn(sock);

        if (oneShot != null) {
            conn.sendLine(oneShot);
            try {
                System.out.println(conn.readLine());
            } catch (ConnectionClosedException e) {
                System.out.println("(connection closed by server)");
            }
            conn.close();
            return;
        }

        System.out.println("connected to " + host + ":" + port
                + ". Commands: SET/GET/DEL/PING/INFO. Ctrl-D to quit.");
        BufferedReader stdin = new BufferedReader(new InputStreamReader(System.in));
        try {
            while (true) {
                System.out.print("> ");
                System.out.flush();
                String line = stdin.readLine();
                if (line == null) {
                    System.out.println();
                    break;
                }
                if (line.isBlank()) continue;
                conn.sendLine(line);
                System.out.println(conn.readLine());
            }
        } catch (ConnectionClosedException e) {
            System.out.println("(connection closed by server)");
        } finally {
            conn.close();
        }
    }
}
