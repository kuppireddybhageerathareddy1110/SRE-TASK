import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Minimal JSON encode/decode for a flat Map&lt;String,String&gt; -- exactly
 * what DUMP needs to send/receive, and nothing more. No external
 * dependency, on purpose (the brief is "standard library only").
 */
public final class Json {
    private Json() {}

    public static String encode(Map<String, String> map) {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, String> e : map.entrySet()) {
            if (!first) sb.append(",");
            first = false;
            sb.append(quote(e.getKey())).append(":").append(quote(e.getValue()));
        }
        return sb.append("}").toString();
    }

    public static Map<String, String> decode(String json) {
        Map<String, String> out = new LinkedHashMap<>();
        int i = skipWs(json, 0);
        if (i >= json.length() || json.charAt(i) != '{') {
            throw new IllegalArgumentException("not a JSON object: " + json);
        }
        i++;
        i = skipWs(json, i);
        if (i < json.length() && json.charAt(i) == '}') {
            return out;
        }
        while (true) {
            i = skipWs(json, i);
            int[] keyEnd = new int[1];
            String key = parseString(json, i, keyEnd);
            i = keyEnd[0];
            i = skipWs(json, i);
            if (json.charAt(i) != ':') throw new IllegalArgumentException("expected ':' at " + i);
            i++;
            i = skipWs(json, i);
            int[] valEnd = new int[1];
            String value = parseString(json, i, valEnd);
            i = valEnd[0];
            out.put(key, value);
            i = skipWs(json, i);
            if (i < json.length() && json.charAt(i) == ',') {
                i++;
                continue;
            }
            break;
        }
        return out;
    }

    private static int skipWs(String s, int i) {
        while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++;
        return i;
    }

    private static String quote(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
                }
            }
        }
        return sb.append("\"").toString();
    }

    private static String parseString(String s, int i, int[] endOut) {
        if (s.charAt(i) != '"') throw new IllegalArgumentException("expected '\"' at " + i);
        i++;
        StringBuilder sb = new StringBuilder();
        while (s.charAt(i) != '"') {
            char c = s.charAt(i);
            if (c == '\\') {
                i++;
                char esc = s.charAt(i);
                switch (esc) {
                    case '"' -> sb.append('"');
                    case '\\' -> sb.append('\\');
                    case 'n' -> sb.append('\n');
                    case 'r' -> sb.append('\r');
                    case 't' -> sb.append('\t');
                    case 'u' -> {
                        String hex = s.substring(i + 1, i + 5);
                        sb.append((char) Integer.parseInt(hex, 16));
                        i += 4;
                    }
                    default -> sb.append(esc);
                }
            } else {
                sb.append(c);
            }
            i++;
        }
        endOut[0] = i + 1;
        return sb.toString();
    }
}
