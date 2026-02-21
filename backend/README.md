# 提钒冶炼智能体（原型后端）

## 运行

```bash
python3 -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

健康检查：

```bash
curl -s http://localhost:8000/api/health
```

## MCP Data Server（JSON-RPC）

列资源：

```bash
curl -s http://localhost:8000/mcp/data \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"resources/list"}'
```

读资源（铁水温度）：

```bash
curl -s http://localhost:8000/mcp/data \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"resources/read","params":{"uri":"resource://plc/iron_ladle/temperature"}}'
```

订阅（SSE 流地址由 subscribe 返回）：

```bash
curl -N http://localhost:8000/api/stream
```

## MCP Tools Server（JSON-RPC）

列工具：

```bash
curl -s http://localhost:8000/mcp/tools \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

调用示例（热平衡与冷料推荐）：

```bash
curl -s http://localhost:8000/mcp/tools \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc":"2.0",
    "id":2,
    "method":"tools/call",
    "params":{
      "name":"calculate_thermal_balance",
      "arguments":{"iron_temp_c":1340,"si_content_pct":0.28,"is_one_can":true}
    }
  }'
```

## Chat（端到端）

```bash
curl -s http://localhost:8000/api/chat \
  -H 'content-type: application/json' \
  -d '{"message":"这炉怎么配？","iron_temp_c":1340,"si_content_pct":0.28,"is_one_can":true}'
```

