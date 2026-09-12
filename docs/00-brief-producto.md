# PROYECTO ATENEA — RPG DE APRENDIZAJE CON IA

> Brief fundacional del producto. Documento de entrada para la auditoría de arquitectura.
> Fecha: 2026-09-10. Autor: Rodrigo Palma.

Quiero desarrollar una aplicación móvil de aprendizaje basada en IA, gamificación y progresión RPG.

La visión del producto es:

> **"Convierte cualquier conocimiento en una aventura."**

El usuario podrá cargar material sobre cualquier tema y la IA transformará ese conocimiento en una **ruta de aprendizaje interactiva, progresiva y gamificada**.

La experiencia debe combinar:

* Aprendizaje personalizado.
* Inteligencia artificial.
* Gamificación.
* RPG medieval.
* Avatares personalizables.
* Experiencia y niveles.
* Rachas.
* Misiones.
* Logros.
* Monedas virtuales.
* Inventario.
* Equipamiento.
* Progresión por conocimientos.
* Estadísticas de aprendizaje.

La referencia conceptual es una combinación entre una plataforma como Duolingo y un RPG medieval, pero **no quiero copiar diseños, personajes, nombres ni elementos protegidos de otras plataformas**.

---

# 1. VISIÓN DEL PRODUCTO

El producto NO debe sentirse como:

> "Un chatbot que genera cursos."

Debe sentirse como:

> **"Un videojuego donde aprender es la forma de avanzar."**

El usuario crea un personaje.

Después selecciona o crea conocimientos que quiere dominar.

La IA analiza documentos y genera una aventura educativa.

El usuario completa:

* Lecciones.
* Preguntas.
* Desafíos.
* Misiones.
* Evaluaciones.

Y como consecuencia:

* Gana XP.
* Gana monedas.
* Sube de nivel.
* Mantiene su racha.
* Desbloquea zonas.
* Obtiene equipamiento.
* Personaliza su personaje.
* Domina conocimientos.

El progreso intelectual debe traducirse visualmente en progreso dentro del mundo del juego.

---

# 2. CONCEPTO CENTRAL

El ciclo principal de la aplicación debe ser:

**Aprender** → **Completar actividades** → **Ganar XP** → **Subir de nivel** → **Obtener monedas/recompensas** → **Desbloquear equipamiento** → **Personalizar personaje** → **Desbloquear nuevos conocimientos** → **Continuar aprendiendo**

Este ciclo debe ser extremadamente claro y satisfactorio.

---

# 3. UNIVERSO MEDIEVAL

La aplicación tendrá una ambientación medieval/fantástica.

El usuario pertenece a un mundo llamado provisionalmente: **El Reino del Conocimiento**. El nombre definitivo debe poder cambiarse posteriormente.

El mundo estará compuesto por diferentes territorios. Ejemplo:

🏰 Reino del Conocimiento
🌲 Bosque de los Fundamentos
🏰 Castillo de SQL
⛰️ Montañas de Data Engineering
🌊 Lago de Data Lakes
🔮 Torre de GCP
⚔️ Reino de las APIs
🏛️ Ciudad de Business Intelligence
🧙 Reino de la Inteligencia Artificial

Estos nombres son ejemplos. La IA o el sistema no debe inventar arbitrariamente una temática que contradiga el contenido. Cada territorio representa una categoría de conocimiento.

---

# 4. AVATAR DEL USUARIO

Cada usuario debe tener un avatar. El avatar es una pieza central del producto. Debe poder personalizarse.

Elementos: Rostro, Cabello, Peinado, Color de cabello, Vestimenta, Armadura, Casco, Corona, Capa, Guantes, Botas, Espadas, Escudos, Arcos, Cetros, Bastones, Accesorios, Mascotas, Monturas.

El sistema debe utilizar un sistema modular de equipamiento para poder agregar nuevos objetos posteriormente.

---

# 5. PERSONAJES

No quiero que el sistema limite rígidamente las clases por género. El usuario debe poder elegir libremente su personaje.

Ejemplos: Guerrero/a, Mago/a, Arquero/a, Caballero/a, Príncipe/Princesa, Hechicero/a, Guardián/a, Elfo/a.

La arquitectura debe permitir agregar nuevas clases posteriormente.

El personaje elegido NO debe afectar las capacidades educativas del usuario. La diferencia es principalmente visual, narrativa y de personalización.

---

# 6. PROGRESIÓN DEL PERSONAJE

El personaje debe tener un nivel global. Ejemplo: **Nivel 1 — Aprendiz** → Nivel 2 → Nivel 3 → ...

El nivel se obtiene principalmente mediante XP. El XP debe provenir de actividades reales de aprendizaje.

No permitir que el usuario pueda obtener cantidades importantes de XP mediante acciones triviales o repetitivas sin valor educativo.

---

# 7. XP

Crear un sistema de experiencia. Ejemplos:

| Acción | XP |
|---|---|
| Completar lección | +50 |
| Respuesta correcta | +10 |
| Completar módulo | +150 |
| Completar desafío | +250 |
| Completar evaluación | +300 |
| Completar misión diaria | +100 |
| Completar una ruta | +1.000 |

Los valores deben ser configurables desde backend. No deben quedar hardcodeados en la aplicación.

---

# 8. DOMINIO POR TEMA

El usuario no debe tener solamente un nivel global. Cada conocimiento debe tener su propia progresión.

Ejemplo:

- **SQL** — Nivel 12 · XP 4.820 · Dominio 87% · Tiempo 18h 32m
- **BigQuery** — Nivel 7 · XP 2.120 · Dominio 63% · Tiempo 9h 14m
- **GCP** — Nivel 4 · XP 890 · Dominio 34% · Tiempo 4h 20m

Esto permite construir un **perfil de conocimiento**.

---

# 9. DOMINIO VS XP

Separar explícitamente:

- **XP**: mide progresión dentro del juego.
- **Tiempo**: mide dedicación.
- **Dominio**: mide conocimiento demostrado.

Un usuario no debe poder alcanzar un dominio alto simplemente acumulando horas. El dominio debe depender principalmente del desempeño en evaluaciones y ejercicios.

---

# 10. RACHAS

Las rachas serán una de las mecánicas principales.

Mostrar: 🔥 Racha actual: 14 días · 🔥 Mejor racha: 37 días

La racha se mantiene realizando una actividad educativa válida cada día.

Debe existir: Racha actual, Mejor racha, Calendario, Días activos, Objetivo diario, Bonificación por racha.

Ejemplo: 7 días → recompensa. 14 días → recompensa. 30 días → recompensa especial. 100 días → recompensa legendaria.

Los valores deben ser configurables.

---

# 11. OBJETIVOS DIARIOS

El usuario debe tener un objetivo diario. Ejemplo: ⏱ Estudiar 20 minutos, o 📚 Completar 3 actividades, o ⭐ Obtener 100 XP.

El usuario debe poder cumplir el objetivo mediante diferentes acciones. No obligar siempre a realizar exactamente la misma actividad.

---

# 12. MISIONES

### Diarias
* Estudia 20 minutos. Completa 3 lecciones. Responde 10 preguntas.

### Semanales
* Estudia 3 horas. Consigue 1.000 XP. Completa un módulo.

### Especiales
* Completa una ruta. Domina un tema. Obtén 90% en una evaluación.

Las misiones deben entregar: XP, Oro, Objetos, Logros, Desbloqueos.

---

# 13. MONEDA VIRTUAL

Crear una economía virtual: 🪙 Oro.

El oro se obtiene mediante: Lecciones, Misiones, Rachas, Logros, Desafíos, Evaluaciones.

El oro se puede utilizar para: comprar ropa, armaduras, armas, accesorios, personalizar el avatar, elementos cosméticos.

La economía debe estar diseñada para evitar inflación y abuso. Los valores deben ser configurables.

---

# 14. GEMAS / MONEDA PREMIUM

Evaluar posteriormente una segunda moneda: 💎 Gemas. No debe formar parte obligatoriamente del MVP.

Puede utilizarse posteriormente para: items exclusivos, personalización premium, protección de racha, elementos cosméticos, eventos especiales.

Nunca diseñar el sistema de forma que pagar sea necesario para aprender. El conocimiento debe poder conseguirse mediante aprendizaje.

---

# 15. INVENTARIO

Cada usuario tendrá un inventario. Categorías: Cabeza, Cuerpo, Arma, Escudo, Capa, Guantes, Botas, Accesorios, Mascota, Montura.

Cada objeto debe tener: Nombre, Descripción, Rareza, Imagen/asset, Categoría, Precio, Requisitos, Estado desbloqueado/bloqueado, Fecha de adquisición.

---

# 16. RAREZAS

⚪ Común · 🟢 Poco común · 🔵 Raro · 🟣 Épico · 🟠 Legendario · 🔴 Mítico

La rareza debe afectar principalmente: apariencia, exclusividad, requisitos, valor cosmético.

No quiero convertir el aprendizaje en un sistema pay-to-win.

---

# 17. EQUIPAMIENTO VINCULADO AL CONOCIMIENTO

Esta es una característica fundamental. Algunos objetos deben desbloquearse mediante aprendizaje.

- ⚔️ Espada del SQL — Requisito: completar ruta SQL.
- 🔮 Cetro de BigQuery — Requisito: dominio BigQuery ≥ 80%.
- 🛡️ Escudo del Data Engineer — Requisito: completar ruta Data Engineering.
- 👑 Corona del Maestro — Requisito: dominar 5 conocimientos.
- 🧙‍♀️ Báculo de la Maestra de IA — Requisito: completar ruta avanzada de Inteligencia Artificial.

Esto hace que el equipamiento represente realmente el conocimiento adquirido.

---

# 18. PERFIL DEL USUARIO

El perfil debe mostrar: Avatar, Nivel global, XP, Racha, Horas estudiadas, Temas dominados, Logros, Equipamiento, Estadísticas.

Ejemplo: **Nivel 18** · ⭐ 12.840 XP · 🔥 32 días · ⏱ 87h 32m · 🧠 8 temas dominados · 🏆 24 logros

El perfil debe sentirse como un perfil de videojuego.

---

# 19. RUTAS DE APRENDIZAJE

El usuario podrá crear una nueva ruta. Ejemplo: **Quiero aprender SQL.**

Puede: escribir el objetivo, seleccionar nivel, subir documentos, seleccionar material existente.

La IA analiza el material y genera: Ruta → Módulos → Temas → Lecciones → Preguntas → Desafíos → Evaluaciones.

---

# 20. EJEMPLO DE RUTA

## ⚔️ Ruta: Maestro de SQL

1. Fundamentos
2. Consultas
3. Filtros
4. Agregaciones
5. JOINs
6. Subconsultas
7. Window Functions
8. Optimización

Cada nivel debe desbloquearse progresivamente.

---

# 21. LECCIONES

Las lecciones deben ser cortas: idealmente entre 5 y 15 minutos.

Cada lección puede incluir: explicación, ejemplo, imagen/diagrama cuando corresponda, pregunta, ejercicio, mini desafío, recompensa.

Al finalizar: 🎉 ¡Lección completada! +50 XP · +20 🪙 · +1 progreso SQL

---

# 22. SISTEMA DE PREGUNTAS

La IA debe generar preguntas utilizando el material cargado.

Tipos: selección múltiple, verdadero/falso, completar, relacionar, ordenar, preguntas abiertas, casos prácticos, ejercicios técnicos.

Para SQL, por ejemplo: "Escribe una consulta que obtenga los 10 clientes con mayor facturación."

La aplicación debe poder evaluar respuestas técnicas cuando corresponda.

---

# 23. EVALUACIONES

Cada módulo debe poder terminar con una evaluación. Ejemplo: **Desafío del Castillo**, 10 preguntas.

Requisitos: 70% para aprobar. 90%: ⭐ recompensa adicional. 100%: 🏆 logro especial.

Si el usuario falla: no pierde todo el progreso. La aplicación debe identificar las debilidades y recomendar repaso.

---

# 24. APRENDIZAJE ADAPTATIVO

La IA debe analizar: errores, tiempo, precisión, intentos, dificultad, temas dominados, temas débiles. Y adaptar el aprendizaje.

Ejemplo: usuario falla JOIN repetidamente. El sistema: 1. Detecta dificultad. 2. Recomienda repaso. 3. Genera explicación diferente. 4. Muestra otro ejemplo. 5. Genera nuevos ejercicios. 6. Vuelve a evaluar.

---

# 25. RAG

La plataforma debe utilizar una arquitectura RAG cuando corresponda.

Flujo: Documento → extracción → fragmentación → embeddings → almacenamiento vectorial → recuperación → modelo de IA → contenido educativo.

El contenido generado debe estar respaldado por las fuentes. La IA debe: priorizar material del usuario, evitar inventar información, identificar información insuficiente, mantener trazabilidad, permitir consultar la fuente original.

---

# 26. TRAZABILIDAD

Cada lección o pregunta debería poder asociarse internamente con: documento, fragmento, fuente, fecha de procesamiento.

Esto permitirá mostrar: "Contenido generado a partir de: documentación X."

---

# 27. MUNDO Y MAPA

Crear una representación visual del mundo. El usuario debe poder avanzar por territorios.

🏰 Reino del Conocimiento → 🌲 Bosque de SQL → 🏰 Castillo de JOINs → ⛰️ Montañas de Data Engineering → 🔮 Torre de BigQuery

Los territorios pueden desbloquearse al completar determinadas rutas.

---

# 28. DASHBOARD PRINCIPAL

La pantalla inicial debe responder inmediatamente: **¿Qué hago ahora?**

Ejemplo:

**Buenos días 👋** · 🔥 21 días de racha · ⭐ 2.450 XP

**Misión de hoy**: Estudia 20 minutos. ██████░░░░ 60%

**Continúa tu aventura**: ⚔️ SQL — JOINs (+50 XP)

**Tus conocimientos**: SQL 82% · BigQuery 54% · GCP 31%

**Estadísticas**: ⏱ 3h 42m esta semana · 🏆 18 logros

---

# 29. ANIMACIONES Y FEEDBACK

Las acciones importantes deben tener feedback inmediato: respuesta correcta ✨ +10 XP · completar lección 🎉 +50 XP · subir de nivel ⚡ LEVEL UP · desbloquear objeto 🏆 ¡Nuevo equipamiento! · mantener racha 🔥 ¡21 días!

Las animaciones deben ser rápidas y elegantes. No sobrecargar la interfaz.

---

# 30. DISEÑO VISUAL

La estética debe ser: medieval, fantasía, RPG, moderna, limpia, premium, colorida, amigable.

No debe parecer una aplicación educativa tradicional. Debe sentirse como un videojuego móvil moderno.

El diseño debe priorizar: avatar, progreso, XP, racha, misiones, recompensas, mundo, equipamiento.

---

# 31. MULTIPLATAFORMA

Priorizar inicialmente **Mobile First**. Evaluar tecnologías como Flutter y React Native.

Seleccionar la alternativa con mejor relación: velocidad, calidad, mantenibilidad, ecosistema, costos, escalabilidad.

No decidir automáticamente sin comparar.

---

# 32. BACKEND

El backend debe gestionar: usuarios, autenticación, rutas, contenido, documentos, progreso, XP, niveles, rachas, misiones, logros, inventario, monedas, equipamiento, evaluaciones, estadísticas.

---

# 33. MODELO DE DATOS

Diseñar entidades similares a: User, Avatar, Character, Equipment, Inventory, Item, Currency, KnowledgeArea, LearningPath, Module, Topic, Lesson, Question, Answer, Assessment, UserProgress, UserTopicProgress, XPTransaction, Streak, Achievement, Mission, Document, KnowledgeBase, Embedding, LearningSession, StudyActivity, Reward.

Desarrollar las relaciones correctamente. Evitar duplicación de información.

---

# 34. SISTEMA DE EVENTOS

Diseñar la gamificación basada en eventos.

Usuario completa lección → Evento LESSON_COMPLETED → Motor de gamificación → +50 XP, +20 oro, actualiza racha, actualiza progreso, evalúa misión, evalúa logros, comprueba desbloqueos.

Esto permitirá agregar nuevas mecánicas sin modificar todo el sistema.

---

# 35. ANALYTICS

Registrar: inicio de sesión, sesiones, tiempo de estudio, lecciones, preguntas, errores, XP, rachas, misiones, logros, compras, items desbloqueados, abandono, retención.

Métricas principales: DAU, WAU, MAU, Retención D1/D7/D30, racha promedio, tiempo promedio, XP promedio, lecciones por usuario, temas completados, dominio promedio.

---

# 36. MONETIZACIÓN FUTURA

No implementar necesariamente en el MVP, pero diseñar la arquitectura para permitir:

- **Free**: número limitado de rutas, IA limitada, equipamiento básico, funcionalidades esenciales.
- **Premium**: más generación IA, rutas ilimitadas, equipamiento exclusivo, personalización avanzada, estadísticas avanzadas.

Nunca bloquear completamente el aprendizaje detrás de un pago.

---

# 37. FUTURO SOCIAL

Posteriormente: amigos, rankings, leaderboards, desafíos, comparación de XP, equipamiento público, perfiles, comunidades, rutas públicas, compartir rutas, eventos.

Diseñar pensando en retención, pero no forma parte necesariamente del MVP.

---

# 38. IA COMO GAME MASTER

Evaluar la posibilidad de que la IA actúe como un **Game Master educativo**: recomendar qué estudiar, crear misiones, crear desafíos, adaptar dificultad, narrar actividades, recomendar repaso, detectar debilidades, generar recompensas educativas, crear narrativa.

No quiero utilizar IA para todo. Utilizar IA únicamente donde aporte valor real.

---

# 39. SEGURIDAD

Autenticación segura, autorización, separación de datos, protección de documentos, rate limiting, protección de APIs, validación de archivos, control de costos de IA, límites de generación, protección contra abuso.

---

# 40. COSTOS

Optimizar: tokens, embeddings, procesamiento documental, storage, base de datos, infraestructura, generación de contenido.

No llamar al modelo de IA innecesariamente. Cuando el contenido ya fue generado, almacenarlo y reutilizarlo. Modelos económicos para tareas simples y más potentes para tareas complejas.

---

# 41. MVP

- **Usuario**: registro, login, perfil.
- **Avatar**: creación, personalización básica, equipamiento básico.
- **Aprendizaje**: crear ruta, cargar documentos, generar ruta con IA, módulos, lecciones, preguntas, evaluaciones.
- **Gamificación**: XP, niveles, oro, rachas, misiones diarias, logros básicos, progreso por tema.
- **RPG**: avatar, inventario, equipamiento, tienda básica, desbloqueo de objetos mediante aprendizaje.
- **Dashboard**: XP, nivel, racha, tiempo, misiones, progreso, continuar aprendizaje.

---

# 42. LO QUE NO DEBE IMPLEMENTARSE EN EL MVP

Multiplayer, PvP, chat entre usuarios, comunidad, leaderboards globales, marketplace entre usuarios, economía compleja, NFTs, blockchain, mundo 3D, combates complejos, sistema de clanes, monetización avanzada.

La prioridad es validar: **¿Las personas realmente quieren aprender utilizando esta mecánica RPG?**

---

# 43. FASES DEL PRODUCTO

1. **Fase 1 — MVP**: aprendizaje + IA + gamificación + avatar.
2. **Fase 2**: más equipamiento + economía + logros + mejores animaciones.
3. **Fase 3**: mundo expandido + narrativa + misiones avanzadas.
4. **Fase 4**: social + rankings + amigos + desafíos.
5. **Fase 5**: marketplace + creadores + rutas públicas.
6. **Fase 6**: plataforma educativa global.

---

# 44. PRINCIPIO FUNDAMENTAL

Evitar convertir la aplicación en "un juego donde ocasionalmente estudias". Debe ser **"una aplicación donde estudiar es el juego"**.

Cada mecánica de gamificación debe estar vinculada al aprendizaje. La progresión del personaje debe representar progreso intelectual.

---

# 45. OBJETIVO FINAL

El usuario elige qué quiere aprender → carga material → la IA construye una ruta → la ruta se transforma en una aventura → el usuario estudia → completa desafíos → gana XP → mantiene su racha → sube de nivel → obtiene oro → desbloquea equipamiento → mejora su personaje → domina nuevos conocimientos → desbloquea nuevas zonas del mundo → continúa aprendiendo.

---

# 46. FORMA DE TRABAJO PARA LA IMPLEMENTACIÓN

Antes de escribir código, realizar una auditoría completa que presente:

1. Análisis del producto. 2. Propuesta de arquitectura. 3. Stack tecnológico recomendado. 4. Arquitectura de IA. 5. Arquitectura RAG. 6. Modelo de datos. 7. Arquitectura del motor de gamificación. 8. Sistema de XP. 9. Sistema de niveles. 10. Sistema de rachas. 11. Sistema de monedas. 12. Sistema de inventario. 13. Sistema de equipamiento. 14. Sistema de logros. 15. Sistema de misiones. 16. Sistema de dominio. 17. Experiencia UX/UI. 18. Pantallas del MVP. 19. Flujo completo del usuario. 20. Arquitectura de eventos. 21. Estrategia de costos. 22. Seguridad. 23. Escalabilidad. 24. Roadmap. 25. Riesgos.

Después identificar: ambigüedades, decisiones pendientes, riesgos técnicos, riesgos de producto, riesgos de gamificación, riesgos de costos, posibles problemas de retención, posible sobreingeniería. Proponer soluciones.

No comenzar la implementación hasta que la arquitectura y el alcance del MVP estén definidos.

---

# 47. CRITERIO DE ÉXITO DEL MVP

El usuario: 1. Crea un personaje. 2. Crea una ruta. 3. Carga material. 4. Recibe una ruta generada por IA. 5. Completa una lección. 6. Gana XP. 7. Gana monedas. 8. Mantiene una racha. 9. Desbloquea un objeto. 10. Equipa el objeto. 11. Visualiza su progreso. 12. Quiere volver a estudiar al día siguiente.

Métrica fundamental: **¿La gamificación aumenta la frecuencia y constancia del aprendizaje?**

---

# 48. PRINCIPIO DE DISEÑO DEL PRODUCTO

La experiencia debe generar constantemente la sensación: **"Estoy progresando."**

🧠 Dominio (intelectual) · ⏱ Horas (temporal) · ⭐ XP (juego) · ⚔️ Nivel (personaje) · 🎒 Equipamiento (colección) · 🔥 Racha (constancia) · 🗺️ Mundo desbloqueado (aventura)

Todo debe conectarse en una experiencia coherente.

---

# 49. FRASE DEL PRODUCTO

> **"Aprende. Juega. Evoluciona."**

La aplicación debe sentirse como un **RPG medieval de conocimiento**, donde cada nuevo aprendizaje hace más poderoso al personaje.

No quiero simplemente una aplicación educativa con elementos medievales. Quiero construir una **experiencia RPG cuyo sistema de progresión esté basado en el aprendizaje real**.
