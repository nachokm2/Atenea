/// Modelos de datos (DTO) de la API de Atenea.
///
/// Cada clase corresponde a un esquema de salida de §7 del contrato. Reglas
/// que se cumplen sin excepción en todo este archivo:
///
/// - Ningún `fromJson` lanza: un campo ausente, nulo o de otro tipo cae al
///   valor por defecto documentado.
/// - Las claves JSON son literalmente las del contrato (`snake_case`); los
///   identificadores Dart van en español.
/// - Los identificadores de entidad son `String` (UUID en texto).
/// - Las marcas de tiempo llegan en UTC ISO-8601 y se exponen en hora local;
///   las fechas de calendario (`local_date`, `assigned_for`, `effective_from`)
///   se conservan como día, sin convertir de zona.
/// - La app **nunca** calcula XP, oro, nivel, dominio ni precios: todo llega
///   resuelto desde el servidor (§1.4 regla 11 y §7.10).
library;

export 'paginacion.dart';

// ---------------------------------------------------------------------------
// Utilidades de lectura tolerante
// ---------------------------------------------------------------------------

/// Marca de los enums que viajan por la API con un valor textual estable.
mixin ClaveApi on Enum {
  /// Valor literal que usa el contrato (por ejemplo `in_progress`).
  String get api;
}

String _normalizar(String valor) =>
    valor.toLowerCase().replaceAll(RegExp('[^a-z0-9]'), '');

/// Busca en [valores] el miembro cuyo [ClaveApi.api] coincide con [bruto].
///
/// Compara primero de forma exacta y luego ignorando mayúsculas y símbolos,
/// porque la base de datos persiste el nombre del miembro en mayúsculas
/// (§1.4 regla 6) aunque la API exponga el valor.
T desdeClaveApi<T extends ClaveApi>(
  List<T> valores,
  Object? bruto,
  T porDefecto,
) {
  if (bruto == null) return porDefecto;
  final String texto = bruto.toString().trim();
  if (texto.isEmpty) return porDefecto;
  for (final T valor in valores) {
    if (valor.api == texto) return valor;
  }
  final String normal = _normalizar(texto);
  for (final T valor in valores) {
    if (_normalizar(valor.api) == normal) return valor;
  }
  for (final T valor in valores) {
    if (_normalizar(valor.name) == normal) return valor;
  }
  return porDefecto;
}

/// Igual que [desdeClaveApi] pero devuelve `null` si el valor es desconocido.
T? desdeClaveApiOpcional<T extends ClaveApi>(List<T> valores, Object? bruto) {
  if (bruto == null) return null;
  final String normal = _normalizar(bruto.toString());
  if (normal.isEmpty) return null;
  for (final T valor in valores) {
    if (_normalizar(valor.api) == normal) return valor;
  }
  for (final T valor in valores) {
    if (_normalizar(valor.name) == normal) return valor;
  }
  return null;
}

/// Convierte una marca de tiempo ISO-8601 UTC a la hora local del dispositivo.
DateTime? fechaHora(Object? valor) {
  if (valor == null) return null;
  if (valor is DateTime) return valor.toLocal();
  final String texto = valor.toString().trim();
  if (texto.isEmpty) return null;
  if (texto.length <= 10 && !texto.contains('T')) return fechaDia(texto);
  final bool tieneZona = texto.endsWith('Z') ||
      texto.endsWith('z') ||
      RegExp(r'[+-]\d{2}:?\d{2}$').hasMatch(texto);
  final DateTime? leida =
      DateTime.tryParse(tieneZona ? texto : '${texto}Z') ?? DateTime.tryParse(texto);
  return leida?.toLocal();
}

/// Convierte un día de calendario (`2026-09-10`) sin desplazarlo de zona.
DateTime? fechaDia(Object? valor) {
  if (valor == null) return null;
  if (valor is DateTime) return DateTime(valor.year, valor.month, valor.day);
  final String texto = valor.toString().trim();
  if (texto.isEmpty) return null;
  final DateTime? leida =
      DateTime.tryParse(texto.length > 10 ? texto.substring(0, 10) : texto);
  if (leida == null) return null;
  return DateTime(leida.year, leida.month, leida.day);
}

// ---------------------------------------------------------------------------
// Enums del contrato (§2). Solo se modelan los que la interfaz consulta.
// ---------------------------------------------------------------------------

/// Rol de la cuenta (`UserRole`).
enum RolUsuario with ClaveApi {
  aprendiz('learner', 'Aprendiz'),
  administrador('admin', 'Administración'),
  soporte('support', 'Soporte');

  const RolUsuario(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible en español.
  final String etiqueta;
  static RolUsuario desdeApi(Object? v) => desdeClaveApi(values, v, aprendiz);
}

/// Orden a la que pertenece el personaje (`CharacterArchetype`).
enum Arquetipo with ClaveApi {
  acero('steel', 'Orden del Acero'),
  arcano('arcane', 'Círculo del Arcano'),
  bosque('forest', 'Hermandad del Bosque'),
  muro('wall', 'Vigilia del Muro'),
  estandarte('banner', 'Compañía del Estandarte'),
  corona('crown', 'Casa de la Corona'),
  runas('runes', 'Cofradía de las Runas'),
  bosqueAntiguo('ancient_forest', 'Linaje del Bosque Antiguo');

  const Arquetipo(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la Orden.
  final String etiqueta;

  /// Las cuatro Órdenes disponibles en el MVP.
  static const List<Arquetipo> delMvp = <Arquetipo>[acero, arcano, bosque, muro];
  static Arquetipo desdeApi(Object? v) => desdeClaveApi(values, v, acero);
}

/// Silueta del avatar (`BodyType`).
enum TipoCuerpo with ClaveApi {
  neutro('neutral', 'Neutra'),
  esbelto('slim', 'Esbelta'),
  robusto('stout', 'Robusta');

  const TipoCuerpo(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la silueta.
  final String etiqueta;
  static TipoCuerpo desdeApi(Object? v) => desdeClaveApi(values, v, neutro);
}

/// Forma gramatical con la que el juego se dirige al usuario (`AddressForm`).
enum FormaTrato with ClaveApi {
  masculino('m', 'Masculino'),
  femenino('f', 'Femenino'),
  neutro('n', 'Neutro');

  const FormaTrato(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la forma de tratamiento.
  final String etiqueta;
  static FormaTrato desdeApi(Object? v) => desdeClaveApi(values, v, neutro);
}

/// Preferencia de tema visual (`ThemePreference`).
enum PreferenciaTema with ClaveApi {
  sistema('system', 'Como el sistema'),
  oscuro('dark', 'Noche del Reino'),
  claro('light', 'Día del Reino');

  const PreferenciaTema(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del tema.
  final String etiqueta;
  static PreferenciaTema desdeApi(Object? v) => desdeClaveApi(values, v, sistema);
}

/// Modo del recordatorio diario (`ReminderMode`).
enum ModoRecordatorio with ClaveApi {
  inteligente('smart', 'Inteligente'),
  manual('manual', 'A una hora fija'),
  apagado('off', 'Sin recordatorio');

  const ModoRecordatorio(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del modo.
  final String etiqueta;
  static ModoRecordatorio desdeApi(Object? v) => desdeClaveApi(values, v, inteligente);
}

/// Categoría de un conocimiento (`KnowledgeCategory`).
enum CategoriaConocimiento with ClaveApi {
  datos('data', 'Datos'),
  programacion('programming', 'Programación'),
  nube('cloud', 'Nube'),
  ia('ai', 'Inteligencia artificial'),
  negocios('business', 'Negocios'),
  idiomas('languages', 'Idiomas'),
  ciencia('science', 'Ciencia'),
  humanidades('humanities', 'Humanidades'),
  artes('arts', 'Artes'),
  salud('health', 'Salud'),
  derecho('law', 'Derecho'),
  otro('other', 'Otros');

  const CategoriaConocimiento(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la categoría.
  final String etiqueta;
  static CategoriaConocimiento desdeApi(Object? v) => desdeClaveApi(values, v, otro);
}

/// Estado de dominio de un conocimiento o de un tema (`KnowledgeAreaStatus`).
enum EstadoDominio with ClaveApi {
  sinEvidencia('no_evidence', 'Sin evidencia'),
  enProgreso('in_progress', 'En progreso'),
  dominado('mastered', 'Dominado'),
  enRiesgo('at_risk', 'En riesgo'),
  debilitado('weakened', 'Debilitado');

  const EstadoDominio(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;

  /// ¿Conviene proponer un repaso? (§6.8).
  bool get pideRepaso => this == enRiesgo || this == debilitado;
  static EstadoDominio desdeApi(Object? v) => desdeClaveApi(values, v, sinEvidencia);
}

/// Estado visual del territorio en el mapa (`TerritoryStatus`).
enum EstadoTerritorio with ClaveApi {
  bruma('fogged', 'En la bruma'),
  descubierto('discovered', 'Descubierto'),
  completado('completed', 'Completado');

  const EstadoTerritorio(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;
  static EstadoTerritorio desdeApi(Object? v) => desdeClaveApi(values, v, bruma);
}

/// Quién creó la ruta (`PathOrigin`).
enum OrigenRuta with ClaveApi {
  reino('seed', 'Ruta del Reino'),
  propia('user', 'Mi ruta');

  const OrigenRuta(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del origen.
  final String etiqueta;
  static OrigenRuta desdeApi(Object? v) => desdeClaveApi(values, v, propia);
}

/// Ciclo de vida del contenido de la ruta (`PathStatus`).
enum EstadoRuta with ClaveApi {
  borrador('draft', 'Borrador'),
  generando('generating', 'Forjando'),
  porRevisar('pending_review', 'Lista para revisar'),
  activa('active', 'Activa'),
  completada('completed', 'Completada'),
  archivada('archived', 'Archivada'),
  fallida('failed', 'No se pudo forjar');

  const EstadoRuta(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;
  static EstadoRuta desdeApi(Object? v) => desdeClaveApi(values, v, borrador);
}

/// Respaldo documental de la ruta (`PathSourceMode`), con valores en español.
enum ModoFuente with ClaveApi {
  conFuente('con_fuente', 'Con material'),
  sinFuente('sin_fuente', 'Sin material'),
  mixta('mixta', 'Mixta');

  const ModoFuente(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del modo.
  final String etiqueta;
  static ModoFuente desdeApi(Object? v) => desdeClaveApi(values, v, conFuente);
}

/// Qué hacer con los temas sin respaldo suficiente (`CoveragePolicy`).
enum PoliticaCobertura with ClaveApi {
  soloFuente('source_only', 'Solo con mi material'),
  conocimientoDelModelo('model_knowledge', 'Completar con el saber del Reino'),
  pedirMas('request_more', 'Pedirme más material');

  const PoliticaCobertura(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la política.
  final String etiqueta;
  static PoliticaCobertura desdeApi(Object? v) =>
      desdeClaveApi(values, v, conocimientoDelModelo);
}

/// Cobertura del material para un tema (`CoverageLevel`).
enum NivelCobertura with ClaveApi {
  completa('full', 'Cubierto por tu material'),
  parcial('partial', 'Cubierto en parte'),
  insuficiente('insufficient', 'Sin respaldo suficiente');

  const NivelCobertura(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la cobertura.
  final String etiqueta;
  static NivelCobertura desdeApi(Object? v) => desdeClaveApi(values, v, completa);
}

/// Nivel declarado por el usuario al crear la ruta (`DeclaredLevel`).
enum NivelDeclarado with ClaveApi {
  principiante('beginner', 'Empiezo de cero'),
  intermedio('intermediate', 'Sé lo básico'),
  avanzado('advanced', 'Quiero profundizar');

  const NivelDeclarado(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del nivel.
  final String etiqueta;
  static NivelDeclarado desdeApi(Object? v) => desdeClaveApi(values, v, principiante);
}

/// Dificultad de una pregunta, tema o módulo (`DifficultyLevel`).
enum Dificultad with ClaveApi {
  facil('easy', 'Fácil'),
  media('medium', 'Media'),
  dificil('hard', 'Difícil');

  const Dificultad(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la dificultad.
  final String etiqueta;
  static Dificultad desdeApi(Object? v) => desdeClaveApi(values, v, media);
}

/// Estado de generación del contenido (`ContentStatus`).
enum EstadoContenido with ClaveApi {
  pendiente('pending', 'Pendiente'),
  generando('generating', 'Forjando'),
  listo('ready', 'Listo'),
  requiereAtencion('needs_attention', 'Requiere atención'),
  reportado('flagged', 'Reportado'),
  reemplazado('superseded', 'Reemplazado');

  const EstadoContenido(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;

  /// ¿Se puede abrir ya el contenido?
  bool get estaDisponible => this == listo;
  static EstadoContenido desdeApi(Object? v) => desdeClaveApi(values, v, pendiente);
}

/// Estado del módulo para un usuario (`ModuleStatus`).
enum EstadoModulo with ClaveApi {
  bloqueado('locked', 'Bloqueado'),
  disponible('available', 'Disponible'),
  enProgreso('in_progress', 'En progreso'),
  completado('completed', 'Completado'),
  dominado('mastered', 'Dominado');

  const EstadoModulo(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;
  static EstadoModulo desdeApi(Object? v) => desdeClaveApi(values, v, bloqueado);
}

/// Estado genérico de progreso de ruta y lección (`ProgressState`).
enum EstadoProgreso with ClaveApi {
  sinEmpezar('not_started', 'Sin empezar'),
  enProgreso('in_progress', 'En curso'),
  completado('completed', 'Completada'),
  archivado('archived', 'Archivada');

  const EstadoProgreso(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;
  static EstadoProgreso desdeApi(Object? v) => desdeClaveApi(values, v, sinEmpezar);
}

/// Tipos de bloque de una lección (`LessonBlockType`).
enum TipoBloque with ClaveApi {
  explicacion('explanation', 'Explicación'),
  ejemplo('example', 'Ejemplo'),
  codigo('code_example', 'Código'),
  diagrama('diagram', 'Diagrama'),
  preguntaIntercalada('inline_question', 'Pregunta'),
  resumen('summary', 'Resumen');

  const TipoBloque(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del tipo de bloque.
  final String etiqueta;
  static TipoBloque desdeApi(Object? v) => desdeClaveApi(values, v, explicacion);
}

/// Los tipos de pregunta del MVP más los reservados (`QuestionType`).
enum TipoPregunta with ClaveApi {
  opcionMultiple('multiple_choice', 'Opción múltiple'),
  verdaderoFalso('true_false', 'Verdadero o falso'),
  completar('fill_blank', 'Completa el hueco'),
  relacionar('matching', 'Relaciona'),
  ordenar('ordering', 'Ordena'),
  respuestaCorta('open_short', 'Respuesta breve'),
  ejercicioSql('sql_exercise', 'Ejercicio SQL'),
  casoEstudio('case_study', 'Caso de estudio'),
  ejercicioCodigo('code_exercise', 'Ejercicio de código');

  const TipoPregunta(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del tipo.
  final String etiqueta;
  static TipoPregunta desdeApi(Object? v) => desdeClaveApi(values, v, opcionMultiple);
}

/// Contexto en el que se respondió una pregunta (`ActivityContext`).
enum ContextoActividad with ClaveApi {
  leccion('lesson', 'Lección'),
  practica('practice', 'Práctica'),
  repaso('review', 'Repaso'),
  desafio('challenge', 'Desafío'),
  evaluacion('assessment', 'Desafío del módulo');

  const ContextoActividad(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del contexto.
  final String etiqueta;
  static ContextoActividad desdeApi(Object? v) => desdeClaveApi(values, v, leccion);
}

/// Tipo de actividad de estudio abierta (`StudyActivityType`).
enum TipoActividad with ClaveApi {
  leccion('lesson', 'Lección'),
  practica('practice', 'Práctica'),
  repaso('review', 'Repaso'),
  desafio('challenge', 'Desafío'),
  evaluacion('assessment', 'Desafío del módulo');

  const TipoActividad(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del tipo de actividad.
  final String etiqueta;
  static TipoActividad desdeApi(Object? v) => desdeClaveApi(values, v, leccion);
}

/// Cómo se corrigió la respuesta (`EvaluationMethod`).
enum MetodoEvaluacion with ClaveApi {
  determinista('deterministic', 'Corrección automática'),
  sandbox('sandbox', 'Ejecución de tu consulta'),
  juez('llm_judge', 'Revisión con IA'),
  pendiente('pending', 'Pendiente de revisión');

  const MetodoEvaluacion(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del método.
  final String etiqueta;
  static MetodoEvaluacion desdeApi(Object? v) => desdeClaveApi(values, v, determinista);
}

/// Resultado de una respuesta individual (`AttemptResult`).
enum ResultadoIntento with ClaveApi {
  correcta('correct', 'Correcta'),
  parcial('partial', 'Casi'),
  incorrecta('incorrect', 'Incorrecta'),
  omitida('skipped', 'Sin responder'),
  porRevisar('needs_review', 'En revisión');

  const ResultadoIntento(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del resultado.
  final String etiqueta;
  static ResultadoIntento desdeApi(Object? v) => desdeClaveApi(values, v, incorrecta);
}

/// Estado de un intento de actividad o de evaluación (`AttemptStatus`).
enum EstadoIntento with ClaveApi {
  enProgreso('in_progress', 'En curso'),
  enviado('submitted', 'Enviado'),
  vencido('expired', 'Vencido'),
  abandonado('abandoned', 'Abandonado');

  const EstadoIntento(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;
  static EstadoIntento desdeApi(Object? v) => desdeClaveApi(values, v, enProgreso);
}

/// Resultado de un intento de evaluación de módulo (`AssessmentOutcome`).
enum ResultadoEvaluacion with ClaveApi {
  reprobado('failed', 'Aún no'),
  aprobado('passed', 'Aprobado'),
  distincion('passed_distinction', 'Aprobado con distinción'),
  perfecto('passed_perfect', 'Perfecto');

  const ResultadoEvaluacion(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del resultado.
  final String etiqueta;

  /// ¿El intento superó el umbral de aprobación?
  bool get aprobo => this != reprobado;
  static ResultadoEvaluacion desdeApi(Object? v) => desdeClaveApi(values, v, reprobado);
}

/// Formato de origen del material (`DocumentType`).
enum TipoDocumento with ClaveApi {
  pdf('pdf', 'PDF'),
  docx('docx', 'Word'),
  markdown('markdown', 'Markdown'),
  txt('txt', 'Texto'),
  textoPegado('pasted_text', 'Texto pegado'),
  url('url', 'Enlace'),
  imagen('image', 'Imagen');

  const TipoDocumento(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del formato.
  final String etiqueta;
  static TipoDocumento desdeApi(Object? v) => desdeClaveApi(values, v, pdf);
}

/// Estado del documento o de una de sus versiones (`DocumentStatus`).
enum EstadoDocumento with ClaveApi {
  subido('uploaded', 'Subido'),
  enCola('queued', 'En cola'),
  extrayendo('extracting', 'Leyendo el material'),
  fragmentando('chunking', 'Ordenando el material'),
  indexando('embedding', 'Indexando'),
  listo('ready', 'Listo'),
  fallido('failed', 'No se pudo procesar'),
  rechazado('rejected', 'Rechazado'),
  reemplazado('superseded', 'Reemplazado'),
  eliminado('deleted', 'Eliminado');

  const EstadoDocumento(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;

  /// ¿Ya se puede usar como material de una ruta?
  bool get estaListo => this == listo;

  /// ¿Sigue procesándose?
  bool get estaEnCurso =>
      this == subido || this == enCola || this == extrayendo || this == fragmentando || this == indexando;
  static EstadoDocumento desdeApi(Object? v) => desdeClaveApi(values, v, subido);
}

/// Naturaleza del fragmento de material (`ChunkType`).
enum TipoFragmento with ClaveApi {
  prosa('prose', 'Texto'),
  codigo('code', 'Código'),
  tabla('table', 'Tabla'),
  lista('list', 'Lista');

  const TipoFragmento(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del tipo de fragmento.
  final String etiqueta;
  static TipoFragmento desdeApi(Object? v) => desdeClaveApi(values, v, prosa);
}

/// Tipo de trabajo de generación o procesamiento (`JobType`).
enum TipoTrabajo with ClaveApi {
  ingestaDocumento('document_ingestion', 'Leyendo tu material'),
  loteEmbeddings('embedding_batch', 'Indexando tu material'),
  disenoRuta('path_design', 'Diseñando la ruta'),
  generacionModulo('module_generation', 'Forjando el módulo'),
  generacionLeccion('lesson_generation', 'Escribiendo las lecciones'),
  generacionPreguntas('question_generation', 'Creando las preguntas'),
  complementoEvaluacion('assessment_complement', 'Preparando el desafío'),
  juicioRespuesta('answer_judgement', 'Revisando tu respuesta'),
  evaluacionSql('sql_evaluation', 'Ejecutando tu consulta'),
  reexplicacion('re_explanation', 'Buscando otra explicación'),
  ejerciciosRemediales('remedial_exercises', 'Preparando práctica'),
  verificacionRespaldo('groundedness_check', 'Verificando el respaldo'),
  narrativa('narrative_generation', 'Escribiendo la crónica'),
  nombreTerritorio('territory_naming', 'Nombrando el territorio');

  const TipoTrabajo(this.api, this.etiqueta);
  @override
  final String api;

  /// Etapa visible mientras el trabajo corre.
  final String etiqueta;
  static TipoTrabajo desdeApi(Object? v) => desdeClaveApi(values, v, disenoRuta);
}

/// Estado de un trabajo de generación (`JobStatus`).
enum EstadoTrabajo with ClaveApi {
  pendiente('pending', 'En cola'),
  ejecutando('running', 'En marcha'),
  logrado('succeeded', 'Listo'),
  fallido('failed', 'Falló'),
  cancelado('cancelled', 'Cancelado'),
  requiereAtencion('needs_attention', 'Requiere atención');

  const EstadoTrabajo(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;

  /// ¿El trabajo terminó, con éxito o sin él?
  bool get termino => this == logrado || this == fallido || this == cancelado;
  static EstadoTrabajo desdeApi(Object? v) => desdeClaveApi(values, v, pendiente);
}

/// Origen del contenido generado (`ProvenanceOrigin`).
enum OrigenContenido with ClaveApi {
  material('source', 'De tu material'),
  saberDelReino('model_knowledge', 'Saber del Reino');

  const OrigenContenido(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del origen.
  final String etiqueta;
  static OrigenContenido desdeApi(Object? v) => desdeClaveApi(values, v, material);
}

/// Qué elemento generado se está trazando (`ProvenanceContentType`).
enum TipoContenido with ClaveApi {
  ruta('path', 'Ruta'),
  modulo('module', 'Módulo'),
  tema('topic', 'Tema'),
  leccion('lesson', 'Lección'),
  bloque('lesson_block', 'Bloque'),
  pregunta('question', 'Pregunta'),
  territorio('territory', 'Territorio'),
  explicacion('explanation', 'Explicación');

  const TipoContenido(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del tipo de contenido.
  final String etiqueta;
  static TipoContenido desdeApi(Object? v) => desdeClaveApi(values, v, bloque);
}

/// Sentido de una transacción del ledger de oro (`LedgerDirection`).
enum SentidoMovimiento with ClaveApi {
  ingreso('credit', 'Ganaste'),
  gasto('debit', 'Gastaste');

  const SentidoMovimiento(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del sentido.
  final String etiqueta;
  static SentidoMovimiento desdeApi(Object? v) => desdeClaveApi(values, v, ingreso);
}

/// Estado de una fecha local en el calendario (`DayStatus`).
enum EstadoDia with ClaveApi {
  inactivo('inactive', 'Sin actividad'),
  activo('active', 'Día activo'),
  gracia('grace', 'Día de gracia'),
  viaje('travel', 'Ajuste por viaje');

  const EstadoDia(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado del día.
  final String etiqueta;

  /// ¿El día cuenta para la racha?
  bool get cuentaParaRacha => this != inactivo;
  static EstadoDia desdeApi(Object? v) => desdeClaveApi(values, v, inactivo);
}

/// Motivo del último cambio de la racha (`StreakChange`).
enum CambioRacha with ClaveApi {
  iniciada('started', 'Racha iniciada'),
  extendida('extended', 'Racha extendida'),
  graciaUsada('grace_used', 'Día de gracia usado'),
  saltoViaje('travel_skip', 'Ajuste por viaje'),
  rota('broken', 'Racha reiniciada');

  const CambioRacha(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del cambio.
  final String etiqueta;
  static CambioRacha desdeApi(Object? v) => desdeClaveApi(values, v, extendida);
}

/// Tipo de objetivo diario (`GoalType`), con valores en español.
enum TipoObjetivo with ClaveApi {
  minutos('minutos', 'minutos', 'Minutos de estudio'),
  actividades('actividades', 'actividades', 'Actividades'),
  xp('xp', 'XP', 'XP del día');

  const TipoObjetivo(this.api, this.unidad, this.etiqueta);
  @override
  final String api;

  /// Palabra que acompaña al número ("20 minutos").
  final String unidad;

  /// Nombre visible del objetivo.
  final String etiqueta;
  static TipoObjetivo desdeApi(Object? v) => desdeClaveApi(values, v, minutos);
}

/// Horizonte de la misión (`MissionScope`), con valores en español.
enum AmbitoMision with ClaveApi {
  diaria('diaria', 'Diarias'),
  semanal('semanal', 'Semanales'),
  especial('especial', 'De ruta');

  const AmbitoMision(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del grupo de misiones.
  final String etiqueta;
  static AmbitoMision desdeApi(Object? v) => desdeClaveApi(values, v, diaria);
}

/// Ciclo de vida de una misión asignada (`MissionStatus`).
enum EstadoMision with ClaveApi {
  activa('active', 'En curso'),
  completada('completed', 'Cumplida'),
  reclamada('claimed', 'Reclamada'),
  expirada('expired', 'Expirada'),
  cancelada('cancelled', 'Cancelada');

  const EstadoMision(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;

  /// ¿Se puede pulsar "Reclamar"?
  bool get sePuedeReclamar => this == completada;
  static EstadoMision desdeApi(Object? v) => desdeClaveApi(values, v, activa);
}

/// Dificultad de la instancia de misión diaria (`MissionTier`).
enum NivelMision with ClaveApi {
  facil('easy', 'Fácil'),
  media('medium', 'Media'),
  dificil('hard', 'Difícil');

  const NivelMision(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del nivel.
  final String etiqueta;
  static NivelMision desdeApi(Object? v) => desdeClaveApi(values, v, media);
}

/// Pestañas de la sala de trofeos (`AchievementCategory`).
enum CategoriaLogro with ClaveApi {
  aprendizaje('learning', 'Aprendizaje'),
  dominio('mastery', 'Dominio'),
  constancia('consistency', 'Constancia'),
  coleccion('collection', 'Colección'),
  exploracion('exploration', 'Exploración'),
  hito('milestone', 'Hitos');

  const CategoriaLogro(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la pestaña.
  final String etiqueta;
  static CategoriaLogro desdeApi(Object? v) => desdeClaveApi(values, v, aprendizaje);
}

/// Nivel de un logro (`AchievementTier`).
enum NivelLogro with ClaveApi {
  bronce('bronze', 'Bronce', 1),
  plata('silver', 'Plata', 2),
  oro('gold', 'Oro', 3),
  unico('single', 'Único', 1);

  const NivelLogro(this.api, this.etiqueta, this.orden);
  @override
  final String api;

  /// Nombre visible del nivel.
  final String etiqueta;

  /// Orden ascendente para pintar la medalla.
  final int orden;
  static NivelLogro desdeApi(Object? v) => desdeClaveApi(values, v, bronce);
}

/// Si el logro se muestra con progreso o como silueta (`AchievementVisibility`).
enum VisibilidadLogro with ClaveApi {
  visible('visible', 'Visible'),
  oculto('hidden', 'Secreto');

  const VisibilidadLogro(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la visibilidad.
  final String etiqueta;
  static VisibilidadLogro desdeApi(Object? v) => desdeClaveApi(values, v, visible);
}

/// Ranura del avatar (`ItemSlot`).
enum RanuraItem with ClaveApi {
  cabeza('head', 'Cabeza'),
  cuerpo('body', 'Cuerpo'),
  capa('cape', 'Capa'),
  guantes('gloves', 'Guantes'),
  botas('boots', 'Botas'),
  arma('weapon', 'Arma'),
  secundaria('offhand', 'Mano secundaria'),
  accesorio('accessory', 'Accesorio'),
  mascota('pet', 'Compañero'),
  montura('mount', 'Montura');

  const RanuraItem(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la ranura.
  final String etiqueta;

  /// Las ocho ranuras activas del MVP (`items.slots_active`).
  static const List<RanuraItem> activas = <RanuraItem>[
    cabeza,
    cuerpo,
    capa,
    guantes,
    botas,
    arma,
    secundaria,
    accesorio,
  ];
  static RanuraItem desdeApi(Object? v) => desdeClaveApi(values, v, accesorio);
}

/// Rareza de un ítem (`ItemRarity`). El color sale de `Rareza` en los tokens.
enum RarezaItem with ClaveApi {
  comun('common', 'Común', 0),
  pocoComun('uncommon', 'Poco común', 1),
  raro('rare', 'Raro', 2),
  epico('epic', 'Épico', 3),
  legendario('legendary', 'Legendario', 4),
  mitico('mythic', 'Mítico', 5);

  const RarezaItem(this.api, this.etiqueta, this.orden);
  @override
  final String api;

  /// Nombre visible de la rareza.
  final String etiqueta;

  /// Orden ascendente de exclusividad.
  final int orden;
  static RarezaItem desdeApi(Object? v) => desdeClaveApi(values, v, comun);
}

/// Origen de un ítem del catálogo o de la instancia poseída (`ItemOrigin`).
enum OrigenItem with ClaveApi {
  inicial('starter', 'Kit inicial'),
  tienda('shop', 'Mercado'),
  logro('achievement', 'Logro'),
  racha('streak', 'Racha'),
  conocimiento('knowledge', 'Se gana aprendiendo'),
  evento('event', 'Evento'),
  mision('mission', 'Misión');

  const OrigenItem(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del origen.
  final String etiqueta;
  static OrigenItem desdeApi(Object? v) => desdeClaveApi(values, v, tienda);
}

/// Quién ve el ítem aunque esté bloqueado (`ItemVisibility`).
enum VisibilidadItem with ClaveApi {
  publico('public', 'Visible'),
  duenio('owner', 'Solo para quien lo posee'),
  oculto('hidden', 'Secreto');

  const VisibilidadItem(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible de la visibilidad.
  final String etiqueta;
  static VisibilidadItem desdeApi(Object? v) => desdeClaveApi(values, v, publico);
}

/// Tipos de condición del DSL de desbloqueo (`RequirementType`).
enum TipoRequisito with ClaveApi {
  rutaCompletada('path_completed', 'Completar una ruta'),
  dominioMinimo('mastery_gte', 'Alcanzar dominio'),
  areasDominadas('areas_mastered_gte', 'Dominar conocimientos'),
  puntajeEvaluacion('assessment_score_gte', 'Puntaje en un desafío'),
  rachaMinima('streak_gte', 'Mantener la racha'),
  nivelMinimo('level_gte', 'Alcanzar un nivel'),
  logroDesbloqueado('achievement_unlocked', 'Desbloquear un logro'),
  leccionesCompletadas('lessons_completed_gte', 'Completar lecciones'),
  dentroDeVentana('within_window', 'Dentro del plazo');

  const TipoRequisito(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del requisito.
  final String etiqueta;
  static TipoRequisito desdeApi(Object? v) => desdeClaveApi(values, v, nivelMinimo);
}

/// Estado de una orden de compra (`PurchaseStatus`).
enum EstadoCompra with ClaveApi {
  completada('completed', 'Completada'),
  revertida('reversed', 'Deshecha');

  const EstadoCompra(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;
  static EstadoCompra desdeApi(Object? v) => desdeClaveApi(values, v, completada);
}

/// Tipos de notificación in-app y push (`NotificationType`).
enum TipoNotificacion with ClaveApi {
  rutaLista('path_ready', 'Tu ruta está lista'),
  generacionFallida('generation_failed', 'Problema al forjar'),
  recordatorioRacha('streak_reminder', 'Recordatorio de racha'),
  ultimaLlamada('streak_last_call', 'Última llamada'),
  hitoCercano('streak_milestone_near', 'Hito cerca'),
  misionDiaria('daily_mission', 'Misiones del día'),
  repasoRecomendado('review_recommended', 'Repaso recomendado'),
  reactivacion('reactivation', 'Te esperamos'),
  itemDesbloqueado('item_unlocked', 'Nuevo equipamiento'),
  logroDesbloqueado('achievement_unlocked', 'Logro desbloqueado'),
  sistema('system', 'Aviso del Reino');

  const TipoNotificacion(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del tipo.
  final String etiqueta;
  static TipoNotificacion desdeApi(Object? v) => desdeClaveApi(values, v, sistema);
}

/// Estado de entrega o lectura de una notificación (`NotificationStatus`).
enum EstadoNotificacion with ClaveApi {
  pendiente('pending', 'Pendiente'),
  enviada('sent', 'Enviada'),
  fallida('failed', 'No entregada'),
  leida('read', 'Leída'),
  descartada('dismissed', 'Descartada');

  const EstadoNotificacion(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del estado.
  final String etiqueta;
  static EstadoNotificacion desdeApi(Object? v) => desdeClaveApi(values, v, pendiente);
}

/// Ámbito al que se refiere un delta de dominio del recibo (§7.10).
enum AmbitoDominio with ClaveApi {
  tema('topic', 'Tema'),
  modulo('module', 'Módulo'),
  conocimiento('knowledge_area', 'Conocimiento'),
  ruta('path', 'Ruta');

  const AmbitoDominio(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del ámbito.
  final String etiqueta;
  static AmbitoDominio desdeApi(Object? v) => desdeClaveApi(values, v, tema);
}

/// Qué se desbloqueó con la última acción (§7.10, sección `unlocks`).
enum TipoDesbloqueo with ClaveApi {
  modulo('module', 'Nuevo módulo'),
  territorio('territory', 'Nuevo territorio'),
  evaluacion('assessment', 'Desafío del módulo'),
  ruta('path', 'Nueva ruta'),
  item('item', 'Nuevo equipamiento'),
  rarezaTienda('shop_rarity', 'Nueva rareza en el Mercado'),
  otro('other', 'Novedad');

  const TipoDesbloqueo(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del desbloqueo.
  final String etiqueta;
  static TipoDesbloqueo desdeApi(Object? v) => desdeClaveApi(values, v, otro);
}

/// Qué propone el botón "Continuar" del panel (§7.8, `continue_action`).
enum TipoAccionContinuar with ClaveApi {
  leccion('lesson', 'Continuar la lección'),
  evaluacion('assessment', 'Enfrentar el desafío'),
  repaso('review', 'Repasar'),
  practica('practice', 'Practicar'),
  crearRuta('create_path', 'Crear mi ruta'),
  verGeneracion('generation', 'Ver cómo avanza'),
  ninguna('none', 'Explorar el Reino');

  const TipoAccionContinuar(this.api, this.etiqueta);
  @override
  final String api;

  /// Texto sugerido para el botón.
  final String etiqueta;
  static TipoAccionContinuar desdeApi(Object? v) => desdeClaveApi(values, v, ninguna);
}

/// Pasos de la cola de celebraciones (§7.10 regla 2 y §5.3 del documento UX).
enum PasoCelebracion with ClaveApi {
  xp('xp', 'Experiencia'),
  oro('gold', 'Oro'),
  dominio('mastery', 'Dominio'),
  racha('streak', 'Racha'),
  subidaNivel('level_up', 'Subida de nivel'),
  item('item', 'Nuevo equipamiento'),
  logro('achievement', 'Logro'),
  mision('mission', 'Misión cumplida');

  const PasoCelebracion(this.api, this.etiqueta);
  @override
  final String api;

  /// Nombre visible del paso.
  final String etiqueta;

  /// Orden canónico si el servidor no envía `presentation_order`.
  static const List<PasoCelebracion> ordenCanonico = <PasoCelebracion>[
    xp,
    oro,
    dominio,
    racha,
    subidaNivel,
    item,
    logro,
    mision,
  ];

  /// Los tres pasos que se presentan como overlay a pantalla completa.
  static const List<PasoCelebracion> deOverlay = <PasoCelebracion>[
    racha,
    subidaNivel,
    item,
  ];
  static PasoCelebracion? desdeApi(Object? v) => desdeClaveApiOpcional(values, v);
}
